# AgenticSeek 성능 튜닝 및 최적화 가이드

## 📋 목차

1. [성능 최적화 개요](#1-성능-최적화-개요)
2. [애플리케이션 레벨 최적화](#2-애플리케이션-레벨-최적화)
3. [데이터베이스 및 캐시 최적화](#3-데이터베이스-및-캐시-최적화)
4. [네트워크 및 인프라 최적화](#4-네트워크-및-인프라-최적화)
5. [LLM 성능 최적화](#5-llm-성능-최적화)
6. [모니터링 및 프로파일링](#6-모니터링-및-프로파일링)
7. [부하 테스트](#7-부하-테스트)
8. [문제 해결](#8-문제-해결)

---

## 1. 성능 최적화 개요

### 1.1 성능 목표

| 메트릭 | 목표 | 현재 | 상태 |
|--------|------|------|------|
| **응답 시간** | < 2초 | 3-5초 | 🟡 개선 필요 |
| **처리량** | 100 req/s | 30 req/s | 🟡 개선 필요 |
| **동시 사용자** | 500명 | 100명 | 🟡 개선 필요 |
| **메모리 사용** | < 2GB | 1.5GB | 🟢 양호 |
| **CPU 사용률** | < 70% | 80% | 🟡 개선 필요 |
| **가용성** | 99.9% | 99.5% | 🟡 개선 필요 |

### 1.2 병목 지점 분석

```bash
# 1. 프로파일링 실행
python -m cProfile -o profile.stats api_secure.py

# 2. 결과 분석
python -c "
import pstats
from pstats import SortKey

p = pstats.Stats('profile.stats')
p.sort_stats(SortKey.CUMULATIVE)
p.print_stats(20)
"

# 3. 주요 병목점:
# - LLM API 호출 (2-3초)
# - 코드 실행 샌드박스 (0.5-1초)
# - 파일 I/O (0.2-0.5초)
# - 입력 검증 (0.1-0.2초)
```

---

## 2. 애플리케이션 레벨 최적화

### 2.1 비동기 처리 최적화

```python
# api_secure_optimized.py

import asyncio
from fastapi import FastAPI, BackgroundTasks
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

app = FastAPI()

# === 1. 커넥션 풀 설정 ===
from fastapi import Depends
from redis import asyncio as aioredis

# Redis 연결 풀
redis_pool = None

@app.on_event("startup")
async def startup():
    global redis_pool
    redis_pool = aioredis.ConnectionPool.from_url(
        "redis://localhost:6379/0",
        max_connections=50,  # 풀 크기
        decode_responses=True
    )

@app.on_event("shutdown")
async def shutdown():
    await redis_pool.disconnect()

async def get_redis():
    return aioredis.Redis(connection_pool=redis_pool)

# === 2. LLM API 호출 최적화 ===
import aiohttp

class LLMClient:
    def __init__(self):
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=100,  # 최대 동시 연결
            limit_per_host=20,
            ttl_dns_cache=300
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout
        )
        return self

    async def __aexit__(self, *args):
        await self.session.close()

    async def query(self, prompt: str):
        async with self.session.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt}
        ) as response:
            return await response.json()

# 전역 LLM 클라이언트
llm_client = None

@app.on_event("startup")
async def init_llm_client():
    global llm_client
    llm_client = await LLMClient().__aenter__()

# === 3. 병렬 처리 ===
@app.post("/query")
async def process_query_optimized(request: QueryRequest):
    # 병렬로 실행 가능한 작업들
    tasks = [
        validate_input(request.query),      # 입력 검증
        get_context_from_cache(request.query),  # 캐시 조회
        check_rate_limit(request.api_key)   # 속도 제한 확인
    ]

    # 동시 실행
    validation, cached, rate_ok = await asyncio.gather(*tasks)

    if not validation.is_valid:
        raise HTTPException(400, validation.errors)

    if cached:
        return cached

    # LLM 호출
    result = await llm_client.query(request.query)

    # 백그라운드에서 캐시 저장 (응답 차단 안 함)
    asyncio.create_task(save_to_cache(request.query, result))

    return result

# === 4. 백그라운드 작업 ===
@app.post("/query-async")
async def process_query_async(
    request: QueryRequest,
    background_tasks: BackgroundTasks
):
    # 즉시 작업 ID 반환
    task_id = generate_task_id()

    # 백그라운드에서 처리
    background_tasks.add_task(
        process_llm_query,
        task_id,
        request.query
    )

    return {"task_id": task_id, "status": "processing"}

@app.get("/query-status/{task_id}")
async def get_query_status(task_id: str):
    # Redis에서 결과 조회
    redis = await get_redis()
    result = await redis.get(f"task:{task_id}")

    if result is None:
        return {"status": "processing"}

    return {"status": "completed", "result": result}
```

### 2.2 캐싱 전략

```python
# caching_optimized.py

from functools import lru_cache
from typing import Optional
import hashlib
import json

# === 1. 메모리 캐시 (LRU) ===
@lru_cache(maxsize=1000)
def get_cached_response(query_hash: str):
    # 자주 요청되는 쿼리 메모리 캐싱
    pass

# === 2. Redis 캐시 ===
class QueryCache:
    def __init__(self, redis):
        self.redis = redis
        self.ttl = 3600  # 1시간

    def get_cache_key(self, query: str) -> str:
        return f"query:{hashlib.sha256(query.encode()).hexdigest()}"

    async def get(self, query: str) -> Optional[dict]:
        key = self.get_cache_key(query)
        cached = await self.redis.get(key)

        if cached:
            # 캐시 히트 메트릭 증가
            await self.redis.incr("cache:hits")
            return json.loads(cached)

        # 캐시 미스 메트릭 증가
        await self.redis.incr("cache:misses")
        return None

    async def set(self, query: str, result: dict):
        key = self.get_cache_key(query)
        await self.redis.setex(
            key,
            self.ttl,
            json.dumps(result)
        )

    async def get_stats(self) -> dict:
        hits = int(await self.redis.get("cache:hits") or 0)
        misses = int(await self.redis.get("cache:misses") or 0)
        total = hits + misses

        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total > 0 else 0
        }

# === 3. 결과 사전 계산 (Warm-up) ===
COMMON_QUERIES = [
    "What is AgenticSeek?",
    "How do I get started?",
    "What are the API endpoints?"
]

async def warmup_cache():
    cache = QueryCache(redis_pool)

    for query in COMMON_QUERIES:
        # 사전에 결과 계산 및 캐싱
        result = await process_query(query)
        await cache.set(query, result)

    print(f"✅ Warmed up {len(COMMON_QUERIES)} queries")

@app.on_event("startup")
async def startup():
    await warmup_cache()
```

### 2.3 데이터베이스 쿼리 최적화

```python
# database_optimized.py

# === 1. 배치 처리 ===
async def save_conversations_batch(conversations: List[dict]):
    # 개별 저장 대신 배치로 처리
    async with db_pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO conversations (id, user_id, query, response, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [(c['id'], c['user_id'], c['query'], c['response'], c['created_at'])
             for c in conversations]
        )

# === 2. 인덱스 추가 ===
"""
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_created_at ON conversations(created_at);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
"""

# === 3. 페이지네이션 ===
async def get_conversations(
    user_id: str,
    page: int = 1,
    page_size: int = 20
):
    offset = (page - 1) * page_size

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM conversations
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id, page_size, offset
        )

        return rows

# === 4. 연결 풀 설정 ===
import asyncpg

db_pool = await asyncpg.create_pool(
    host='localhost',
    database='agenticseek',
    user='postgres',
    password='password',
    min_size=10,  # 최소 연결
    max_size=50,  # 최대 연결
    max_queries=50000,  # 연결당 최대 쿼리
    max_inactive_connection_lifetime=300  # 5분
)
```

---

## 3. 데이터베이스 및 캐시 최적화

### 3.1 Redis 설정 최적화

```conf
# redis.conf

# === 메모리 설정 ===
maxmemory 2gb
maxmemory-policy allkeys-lru  # LRU 제거 정책

# === 지속성 최적화 (성능 우선) ===
save 900 1     # 15분마다 1개 이상 변경시 저장
save 300 10    # 5분마다 10개 이상 변경시 저장
save 60 10000  # 1분마다 10000개 이상 변경시 저장

# AOF 비활성화 (캐시용도)
appendonly no

# === 네트워크 최적화 ===
tcp-backlog 511
tcp-keepalive 300
timeout 0

# === 성능 설정 ===
slowlog-log-slower-than 10000  # 10ms 이상 느린 쿼리 로깅
slowlog-max-len 128

# === 클라이언트 연결 ===
maxclients 10000
```

```bash
# Redis 성능 테스트
redis-benchmark -h localhost -p 6379 -n 100000 -c 50

# 결과 예시:
# SET: 89285.71 requests per second
# GET: 92592.59 requests per second
```

### 3.2 파일 시스템 최적화

```python
# filesystem_optimized.py

import aiofiles
import asyncio
from pathlib import Path

# === 1. 비동기 파일 I/O ===
class ConversationStore:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.write_queue = asyncio.Queue()
        self.writer_task = None

    async def start(self):
        # 백그라운드 writer 시작
        self.writer_task = asyncio.create_task(self._writer_loop())

    async def _writer_loop(self):
        while True:
            # 큐에서 배치로 가져오기
            batch = []
            try:
                # 최대 1초 대기 또는 100개 수집
                for _ in range(100):
                    item = await asyncio.wait_for(
                        self.write_queue.get(),
                        timeout=1.0
                    )
                    batch.append(item)
            except asyncio.TimeoutError:
                pass

            if batch:
                await self._write_batch(batch)

    async def _write_batch(self, batch: List[dict]):
        # 배치로 파일 쓰기
        tasks = [
            self._write_file(item['path'], item['content'])
            for item in batch
        ]
        await asyncio.gather(*tasks)

    async def _write_file(self, path: Path, content: str):
        async with aiofiles.open(path, 'w') as f:
            await f.write(content)

    async def save(self, conversation_id: str, content: dict):
        # 큐에 추가만 하고 즉시 반환
        await self.write_queue.put({
            'path': self.base_path / f"{conversation_id}.json",
            'content': json.dumps(content)
        })

# === 2. 메모리 맵 파일 (대용량 읽기) ===
import mmap

def read_large_file_optimized(filepath: str):
    with open(filepath, 'r+b') as f:
        # 메모리 맵 생성
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
            # 파일 내용 처리
            content = mmapped.read()
            return content.decode('utf-8')
```

---

## 4. 네트워크 및 인프라 최적화

### 4.1 Nginx 최적화

```nginx
# nginx.conf (최적화)

http {
    # === 워커 프로세스 최적화 ===
    worker_processes auto;  # CPU 코어 수만큼 자동
    worker_rlimit_nofile 100000;

    events {
        worker_connections 4096;
        use epoll;  # Linux용 고성능 이벤트 모델
        multi_accept on;
    }

    # === 연결 최적화 ===
    keepalive_timeout 65;
    keepalive_requests 100;

    # === 버퍼 최적화 ===
    client_body_buffer_size 128k;
    client_max_body_size 10m;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 4k;
    output_buffers 1 32k;
    postpone_output 1460;

    # === 타임아웃 최적화 ===
    client_header_timeout 10;
    client_body_timeout 10;
    send_timeout 10;

    # === Gzip 압축 ===
    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/rss+xml
        application/atom+xml
        image/svg+xml;

    # === 캐싱 ===
    proxy_cache_path /var/cache/nginx levels=1:2
                     keys_zone=api_cache:10m
                     max_size=1g
                     inactive=60m;

    # === Upstream 최적화 ===
    upstream agenticseek_backend {
        # 연결 풀링
        keepalive 32;
        keepalive_requests 100;
        keepalive_timeout 60s;

        # 로드 밸런싱 (least_conn 알고리즘)
        least_conn;

        server 127.0.0.1:7777 max_fails=3 fail_timeout=30s;
        server 127.0.0.1:7778 max_fails=3 fail_timeout=30s;
        server 127.0.0.1:7779 max_fails=3 fail_timeout=30s;
    }

    server {
        listen 443 ssl http2;

        # === HTTP/2 최적화 ===
        http2_max_concurrent_streams 128;
        http2_recv_timeout 30s;

        # === 캐싱 설정 ===
        location /query {
            proxy_pass http://agenticseek_backend;

            # POST 요청도 캐싱 (동일 body)
            proxy_cache api_cache;
            proxy_cache_methods GET POST;
            proxy_cache_key "$request_uri|$request_body";
            proxy_cache_valid 200 5m;
            add_header X-Cache-Status $upstream_cache_status;

            # 연결 최적화
            proxy_http_version 1.1;
            proxy_set_header Connection "";
        }

        # === 정적 파일 캐싱 ===
        location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### 4.2 시스템 레벨 최적화

```bash
# /etc/sysctl.conf

# === 네트워크 최적화 ===
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535

# TCP 연결 재사용
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15

# TCP 윈도우 크기
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216

# 파일 디스크립터
fs.file-max = 2097152

# 적용
sudo sysctl -p
```

```bash
# 사용자별 제한 수정
# /etc/security/limits.conf

*  soft  nofile  100000
*  hard  nofile  100000
*  soft  nproc   100000
*  hard  nproc   100000
```

---

## 5. LLM 성능 최적화

### 5.1 Ollama 최적화

```bash
# === 1. 모델 사전 로드 ===
# 서버 시작시 모델을 메모리에 로드
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "warmup",
  "keep_alive": -1  # 메모리에 계속 유지
}'

# === 2. 배치 처리 ===
# 여러 요청을 묶어서 처리
```

```python
# llm_optimized.py

class OllamaClient:
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.semaphore = asyncio.Semaphore(10)  # 동시 요청 제한

    async def query_batch(self, prompts: List[str]):
        tasks = [
            self._query_single(prompt)
            for prompt in prompts
        ]
        return await asyncio.gather(*tasks)

    async def _query_single(self, prompt: str):
        async with self.semaphore:
            async with self.session.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "options": {
                        "num_predict": 128,  # 최대 토큰 제한
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_ctx": 2048  # 컨텍스트 윈도우
                    }
                }
            ) as response:
                return await response.json()

# === 3. 스트리밍 응답 ===
async def stream_llm_response(prompt: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": True  # 스트리밍 활성화
            }
        ) as response:
            async for line in response.content:
                if line:
                    yield json.loads(line)

@app.post("/query-stream")
async def query_stream(request: QueryRequest):
    async def generate():
        async for chunk in stream_llm_response(request.query):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

### 5.2 프롬프트 최적화

```python
# prompt_optimization.py

# === 1. 프롬프트 압축 ===
def compress_prompt(long_prompt: str) -> str:
    # 불필요한 단어 제거
    compressed = long_prompt.replace("please", "")
    compressed = compressed.replace("I would like you to", "")

    # 핵심만 추출
    return compressed.strip()

# === 2. 토큰 계산 및 제한 ===
import tiktoken

def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def truncate_to_tokens(text: str, max_tokens: int = 4000) -> str:
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    tokens = encoding.encode(text)

    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        return encoding.decode(tokens)

    return text

# === 3. 컨텍스트 캐싱 ===
class ContextCache:
    def __init__(self):
        self.cache = {}

    def get_cached_context(self, conversation_id: str) -> Optional[str]:
        return self.cache.get(conversation_id)

    def save_context(self, conversation_id: str, context: str):
        # 최근 10개 메시지만 유지
        messages = context.split("\n")
        if len(messages) > 10:
            context = "\n".join(messages[-10:])

        self.cache[conversation_id] = context
```

---

## 6. 모니터링 및 프로파일링

### 6.1 성능 메트릭 수집

```python
# metrics.py

from prometheus_client import Counter, Histogram, Gauge
import time

# === Prometheus 메트릭 ===
REQUEST_COUNT = Counter(
    'agenticseek_requests_total',
    'Total request count',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'agenticseek_request_duration_seconds',
    'Request latency',
    ['endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ACTIVE_REQUESTS = Gauge(
    'agenticseek_active_requests',
    'Number of active requests'
)

LLM_LATENCY = Histogram(
    'agenticseek_llm_duration_seconds',
    'LLM query latency',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# === 미들웨어 ===
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    ACTIVE_REQUESTS.inc()

    try:
        response = await call_next(request)

        # 메트릭 기록
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(
            endpoint=request.url.path
        ).observe(duration)

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()

        # 응답 헤더에 추가
        response.headers["X-Process-Time"] = str(duration)

        return response
    finally:
        ACTIVE_REQUESTS.dec()

# === 메트릭 엔드포인트 ===
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

### 6.2 APM (Application Performance Monitoring)

```python
# apm_integration.py

# === New Relic 통합 ===
import newrelic.agent

newrelic.agent.initialize('newrelic.ini')

@newrelic.agent.background_task()
async def process_llm_query(query: str):
    # 자동으로 트레이싱됨
    pass

# === Datadog 통합 ===
from ddtrace import tracer

@tracer.wrap(service="agenticseek", resource="process_query")
async def process_query(query: str):
    with tracer.trace("llm.query") as span:
        span.set_tag("query_length", len(query))
        result = await llm_client.query(query)
        span.set_tag("response_length", len(result))
        return result
```

---

## 7. 부하 테스트

### 7.1 Locust 부하 테스트

```python
# loadtest/locustfile.py

from locust import HttpUser, task, between
import json

class AgenticSeekUser(HttpUser):
    wait_time = between(1, 3)  # 요청 간 1-3초 대기

    def on_start(self):
        # 테스트 시작시 API 키 설정
        self.api_key = "test-api-key-here"
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

    @task(3)  # 가중치 3
    def query_simple(self):
        self.client.post(
            "/query",
            headers=self.headers,
            json={"query": "What is 2+2?", "tts_enabled": False}
        )

    @task(1)  # 가중치 1
    def query_complex(self):
        self.client.post(
            "/query",
            headers=self.headers,
            json={
                "query": "Explain quantum computing in detail",
                "tts_enabled": False
            }
        )

    @task(5)  # 가중치 5
    def health_check(self):
        self.client.get("/health")
```

```bash
# 실행
locust -f loadtest/locustfile.py --host=https://app.company.com

# CLI 모드 (웹 UI 없이)
locust -f loadtest/locustfile.py \
    --host=https://app.company.com \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless

# 결과:
# Type     Name                # reqs   # fails   Avg    Min    Max  Median   req/s
# POST     /query               5000      0       850    120    3200   780      16.7
# GET      /health             15000      0        15      5      50    12      50.0
```

### 7.2 Apache Bench

```bash
# === 동시성 테스트 ===
ab -n 10000 -c 100 \
   -H "X-API-Key: your-api-key" \
   -p query.json \
   -T "application/json" \
   https://app.company.com/query

# query.json:
# {"query": "test", "tts_enabled": false}

# 결과 분석:
# Requests per second: 87.32 [#/sec]
# Time per request: 1145.2 [ms] (mean)
# Time per request: 11.452 [ms] (mean, across all concurrent requests)
```

### 7.3 K6 스트레스 테스트

```javascript
// k6_test.js

import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 100 },  // 램프 업
    { duration: '5m', target: 100 },  // 지속
    { duration: '2m', target: 200 },  // 스파이크
    { duration: '5m', target: 200 },  // 높은 부하
    { duration: '2m', target: 0 },    // 램프 다운
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95%가 2초 이내
    http_req_failed: ['rate<0.01'],     // 에러율 1% 이하
  },
};

export default function () {
  const url = 'https://app.company.com/query';
  const payload = JSON.stringify({
    query: 'What is AgenticSeek?',
    tts_enabled: false,
  });

  const params = {
    headers: {
      'X-API-Key': 'your-api-key',
      'Content-Type': 'application/json',
    },
  };

  let response = http.post(url, payload, params);

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 2s': (r) => r.timings.duration < 2000,
  });

  sleep(1);
}
```

```bash
# 실행
k6 run k6_test.js

# 결과:
# ✓ status is 200
# ✓ response time < 2s
#
# checks.........................: 100.00% ✓ 50000   ✗ 0
# http_req_duration..............: avg=850ms   min=120ms  max=3s
# http_reqs......................: 50000   83.33/s
```

---

## 8. 문제 해결

### 8.1 높은 응답 시간

```bash
# 1. 병목점 식별
python -m cProfile -o profile.stats api_secure.py

# 2. 느린 쿼리 확인 (Redis)
redis-cli slowlog get 10

# 3. 네트워크 지연 확인
curl -w "@curl-format.txt" -o /dev/null -s https://app.company.com/health

# curl-format.txt:
#   time_namelookup:  %{time_namelookup}\n
#   time_connect:  %{time_connect}\n
#   time_starttransfer:  %{time_starttransfer}\n
#   time_total:  %{time_total}\n

# 4. LLM 지연 확인
time curl http://localhost:11434/api/generate -d '{"model":"mistral","prompt":"test"}'
```

### 8.2 높은 메모리 사용

```bash
# 1. 메모리 프로파일링
pip install memory_profiler
python -m memory_profiler api_secure.py

# 2. 메모리 누수 확인
import tracemalloc

tracemalloc.start()

# ... 코드 실행 ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)

# 3. Redis 메모리 확인
redis-cli info memory
```

### 8.3 높은 CPU 사용

```bash
# 1. CPU 프로파일링
py-spy record -o profile.svg -- python api_secure.py

# 2. 프로세스 모니터링
htop

# 3. 스레드 분석
ps -eLf | grep python
```

---

## 부록: 성능 체크리스트

### 애플리케이션
- [ ] 비동기 처리 구현 (async/await)
- [ ] 연결 풀 설정 (DB, Redis, HTTP)
- [ ] 캐싱 전략 구현
- [ ] 배치 처리 적용
- [ ] 백그라운드 작업 분리

### 데이터베이스
- [ ] 인덱스 추가
- [ ] 쿼리 최적화
- [ ] 연결 풀 설정
- [ ] 페이지네이션 구현

### 인프라
- [ ] Nginx 최적화
- [ ] 시스템 파라미터 튜닝
- [ ] 로드 밸런싱 설정
- [ ] CDN 활용

### 모니터링
- [ ] 메트릭 수집 (Prometheus)
- [ ] 로깅 설정
- [ ] APM 통합
- [ ] 알림 설정

### 테스트
- [ ] 부하 테스트 실행
- [ ] 스트레스 테스트
- [ ] 성능 회귀 테스트

---

**문서 버전**: 1.0
**최종 수정**: 2025-11-02
**작성자**: Performance Team
