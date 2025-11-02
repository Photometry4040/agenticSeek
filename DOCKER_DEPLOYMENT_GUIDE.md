# AgenticSeek Docker 배포 가이드

## 📋 목차

1. [Docker 배포 개요](#1-docker-배포-개요)
2. [Docker 이미지 빌드](#2-docker-이미지-빌드)
3. [Docker Compose 설정](#3-docker-compose-설정)
4. [프로덕션 배포](#4-프로덕션-배포)
5. [Kubernetes 배포](#5-kubernetes-배포)
6. [모니터링 및 로깅](#6-모니터링-및-로깅)
7. [문제 해결](#7-문제-해결)

---

## 1. Docker 배포 개요

### 1.1 장점

- ✅ **환경 일관성**: 개발/스테이징/프로덕션 동일 환경
- ✅ **격리성**: 호스트 시스템과 완전 격리
- ✅ **확장성**: 쉬운 수평 확장 및 오케스트레이션
- ✅ **이식성**: 어떤 클라우드/온프레미스에서도 동일하게 작동
- ✅ **버전 관리**: 이미지 태깅으로 롤백 용이

### 1.2 아키텍처

```
┌─────────────────────────────────────────┐
│         Nginx (Reverse Proxy)           │
│         Port 443 (HTTPS)                │
└──────────────┬──────────────────────────┘
               │
┌──────────────┴──────────────────────────┐
│      AgenticSeek API Container          │
│      Port 7777 (Internal)               │
│      - FastAPI                          │
│      - Security Patches                 │
│      - Code Sandbox                     │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┴───────────┐
    │                      │
┌───┴────┐          ┌──────┴───────┐
│ Redis  │          │   Ollama     │
│ Cache  │          │   LLM Server │
└────────┘          └──────────────┘
```

---

## 2. Docker 이미지 빌드

### 2.1 Dockerfile 생성

```dockerfile
# /home/user/agenticSeek/Dockerfile

FROM python:3.10-slim

# 메타데이터
LABEL maintainer="security@company.com"
LABEL version="1.0.0-secure"
LABEL description="AgenticSeek Secure API with all security patches"

# 환경변수
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# 작업 디렉토리
WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 복사 및 설치
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install RestrictedPython uvicorn[standard]

# 애플리케이션 코드 복사
COPY . /app/

# 보안 패치 검증
RUN python security/quick_scan.py || echo "Warning: Security scan found issues"

# 비-root 사용자 생성
RUN useradd -m -u 1000 agenticseek && \
    chown -R agenticseek:agenticseek /app

# 로그 디렉토리 생성
RUN mkdir -p /app/.logs /app/conversations /app/.screenshots && \
    chown -R agenticseek:agenticseek /app/.logs /app/conversations /app/.screenshots

# 비-root로 실행
USER agenticseek

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7777/health || exit 1

# 포트 노출
EXPOSE 7777

# 실행 명령
CMD ["python", "api_secure.py"]
```

### 2.2 .dockerignore 생성

```bash
# .dockerignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.env
.env.local
*.log
.git/
.gitignore
.vscode/
.idea/
*.md
!README.md
conversations/
.screenshots/
.logs/
*.db
*.sqlite
```

### 2.3 이미지 빌드

```bash
# 개발 이미지
docker build -t agenticseek:dev .

# 프로덕션 이미지 (최적화)
docker build -t agenticseek:1.0.0 \
  --build-arg ENVIRONMENT=production \
  --no-cache .

# 이미지 확인
docker images | grep agenticseek

# 이미지 크기 최적화 확인
docker history agenticseek:1.0.0
```

### 2.4 Multi-stage Build (최적화)

```dockerfile
# Dockerfile.optimized

# Stage 1: 빌드 단계
FROM python:3.10-slim AS builder

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt && \
    pip install --user RestrictedPython uvicorn[standard]

# Stage 2: 런타임 단계
FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지 (최소한만)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 빌드 단계에서 설치한 패키지 복사
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 애플리케이션 코드
COPY . /app/

# 비-root 사용자
RUN useradd -m -u 1000 agenticseek && \
    mkdir -p /app/.logs /app/conversations && \
    chown -R agenticseek:agenticseek /app

USER agenticseek

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7777/health || exit 1

EXPOSE 7777

CMD ["python", "api_secure.py"]
```

```bash
# 최적화된 이미지 빌드
docker build -f Dockerfile.optimized -t agenticseek:1.0.0-slim .
```

---

## 3. Docker Compose 설정

### 3.1 docker-compose.yml

```yaml
# docker-compose.yml
version: '3.8'

services:
  # AgenticSeek API
  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: agenticseek:latest
    container_name: agenticseek-api
    restart: unless-stopped

    # 환경변수
    env_file:
      - .env

    # 포트
    ports:
      - "7777:7777"

    # 볼륨
    volumes:
      - ./conversations:/app/conversations
      - ./screenshots:/app/.screenshots
      - ./logs:/app/.logs
      - ./.env:/app/.env:ro  # 읽기 전용

    # 의존성
    depends_on:
      redis:
        condition: service_healthy
      ollama:
        condition: service_started

    # 리소스 제한
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G

    # 헬스체크
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7777/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    # 네트워크
    networks:
      - agenticseek-network

    # 보안 설정
    security_opt:
      - no-new-privileges:true

    # 로깅
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # Redis
  redis:
    image: redis:7-alpine
    container_name: agenticseek-redis
    restart: unless-stopped

    command: redis-server --requirepass ${REDIS_PASSWORD:-changeme}

    ports:
      - "6379:6379"

    volumes:
      - redis-data:/data

    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

    networks:
      - agenticseek-network

    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

  # Ollama (LLM 서버)
  ollama:
    image: ollama/ollama:latest
    container_name: agenticseek-ollama
    restart: unless-stopped

    ports:
      - "11434:11434"

    volumes:
      - ollama-data:/root/.ollama

    networks:
      - agenticseek-network

    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

    # GPU 지원 (선택사항)
    # runtime: nvidia
    # environment:
    #   - NVIDIA_VISIBLE_DEVICES=all

  # Nginx (리버스 프록시)
  nginx:
    image: nginx:alpine
    container_name: agenticseek-nginx
    restart: unless-stopped

    ports:
      - "80:80"
      - "443:443"

    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx-logs:/var/log/nginx

    depends_on:
      - api

    networks:
      - agenticseek-network

    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3

# 볼륨
volumes:
  redis-data:
    driver: local
  ollama-data:
    driver: local
  nginx-logs:
    driver: local

# 네트워크
networks:
  agenticseek-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### 3.2 Nginx 설정

```nginx
# nginx/nginx.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_types text/plain text/css application/json application/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

    upstream agenticseek_backend {
        server api:7777;
        keepalive 32;
    }

    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name app.company.com;

        # SSL
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # 보안 헤더
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # Rate limiting
        limit_req zone=api_limit burst=20 nodelay;

        # 헬스체크 (로그 없음)
        location /health {
            proxy_pass http://agenticseek_backend/health;
            access_log off;
        }

        # API 엔드포인트
        location / {
            proxy_pass http://agenticseek_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;

            proxy_buffering off;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
        }
    }
}
```

### 3.3 실행 및 관리

```bash
# 1. 환경변수 설정
cp .env.example .env
nano .env  # 설정 편집

# 2. API 키 생성
python security/tools/generate_api_keys.py --count 3 --export

# 3. Docker Compose로 시작
docker-compose up -d

# 4. 로그 확인
docker-compose logs -f api

# 5. 상태 확인
docker-compose ps

# 6. 특정 서비스 재시작
docker-compose restart api

# 7. 중지
docker-compose down

# 8. 완전 삭제 (볼륨 포함)
docker-compose down -v
```

---

## 4. 프로덕션 배포

### 4.1 docker-compose.prod.yml

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  api:
    image: registry.company.com/agenticseek:1.0.0
    container_name: agenticseek-api-prod
    restart: always

    env_file:
      - .env.production

    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO

    volumes:
      - /data/agenticseek/conversations:/app/conversations
      - /data/agenticseek/logs:/app/.logs
      - /secrets/.env:/app/.env:ro

    depends_on:
      redis:
        condition: service_healthy

    deploy:
      replicas: 3  # 3개 인스턴스
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback

    networks:
      - agenticseek-prod

    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://logs.company.com:514"
        tag: "agenticseek-api"

  redis:
    image: redis:7-alpine
    restart: always

    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 1gb
      --maxmemory-policy allkeys-lru
      --save 60 1000
      --appendonly yes

    volumes:
      - /data/redis:/data

    networks:
      - agenticseek-prod

    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G

  nginx:
    image: nginx:alpine
    restart: always

    ports:
      - "443:443"
      - "80:80"

    volumes:
      - ./nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/nginx/ssl:ro
      - /var/log/nginx:/var/log/nginx

    depends_on:
      - api

    networks:
      - agenticseek-prod

networks:
  agenticseek-prod:
    driver: overlay
    attachable: true
```

### 4.2 프로덕션 배포 스크립트

```bash
#!/bin/bash
# deploy-docker.sh

set -e

ENV=${1:-production}
VERSION=${2:-latest}

echo "🚀 Deploying AgenticSeek to $ENV (version: $VERSION)"

# 1. 이미지 빌드
echo "📦 Building Docker image..."
docker build -t agenticseek:$VERSION .

# 2. 이미지 태그
echo "🏷️  Tagging image..."
docker tag agenticseek:$VERSION registry.company.com/agenticseek:$VERSION
docker tag agenticseek:$VERSION registry.company.com/agenticseek:latest

# 3. 레지스트리 푸시
echo "⬆️  Pushing to registry..."
docker push registry.company.com/agenticseek:$VERSION
docker push registry.company.com/agenticseek:latest

# 4. 보안 스캔
echo "🔒 Running security scan..."
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image registry.company.com/agenticseek:$VERSION

# 5. 배포
echo "🚢 Deploying to $ENV..."
if [ "$ENV" = "production" ]; then
  docker stack deploy -c docker-compose.prod.yml agenticseek
else
  docker-compose -f docker-compose.yml up -d
fi

# 6. 헬스체크
echo "🏥 Waiting for health check..."
sleep 10
for i in {1..30}; do
  if curl -f http://localhost:7777/health; then
    echo "✅ Deployment successful!"
    exit 0
  fi
  echo "Waiting... ($i/30)"
  sleep 2
done

echo "❌ Health check failed!"
exit 1
```

```bash
# 실행 권한
chmod +x deploy-docker.sh

# 배포
./deploy-docker.sh production 1.0.0
```

---

## 5. Kubernetes 배포

### 5.1 Kubernetes Manifests

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: agenticseek
  labels:
    name: agenticseek
---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agenticseek-config
  namespace: agenticseek
data:
  BACKEND_PORT: "7777"
  LOG_LEVEL: "INFO"
  ENVIRONMENT: "production"
---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: agenticseek-secrets
  namespace: agenticseek
type: Opaque
stringData:
  AGENTICSEEK_API_KEYS: "key1,key2,key3"
  OPENAI_API_KEY: "sk-..."
  REDIS_PASSWORD: "secure-password"
---
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agenticseek-api
  namespace: agenticseek
  labels:
    app: agenticseek
    tier: backend
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: agenticseek
      tier: backend
  template:
    metadata:
      labels:
        app: agenticseek
        tier: backend
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "7777"
        prometheus.io/path: "/metrics"
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000

      containers:
      - name: api
        image: registry.company.com/agenticseek:1.0.0
        imagePullPolicy: IfNotPresent

        ports:
        - containerPort: 7777
          name: http
          protocol: TCP

        env:
        - name: BACKEND_PORT
          valueFrom:
            configMapKeyRef:
              name: agenticseek-config
              key: BACKEND_PORT

        envFrom:
        - configMapRef:
            name: agenticseek-config
        - secretRef:
            name: agenticseek-secrets

        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi

        livenessProbe:
          httpGet:
            path: /health
            port: 7777
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /health
            port: 7777
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3

        volumeMounts:
        - name: logs
          mountPath: /app/.logs
        - name: conversations
          mountPath: /app/conversations

      volumes:
      - name: logs
        emptyDir: {}
      - name: conversations
        persistentVolumeClaim:
          claimName: agenticseek-pvc
---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: agenticseek-api
  namespace: agenticseek
  labels:
    app: agenticseek
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 7777
    protocol: TCP
    name: http
  selector:
    app: agenticseek
    tier: backend
---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: agenticseek-ingress
  namespace: agenticseek
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "10"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - app.company.com
    secretName: agenticseek-tls
  rules:
  - host: app.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: agenticseek-api
            port:
              number: 80
---
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agenticseek-hpa
  namespace: agenticseek
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agenticseek-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 5.2 Kubernetes 배포

```bash
# 1. 네임스페이스 생성
kubectl apply -f k8s/namespace.yaml

# 2. ConfigMap 및 Secret
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 3. 배포
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml

# 4. 상태 확인
kubectl get all -n agenticseek

# 5. 로그 확인
kubectl logs -f -n agenticseek -l app=agenticseek

# 6. 스케일링
kubectl scale deployment agenticseek-api -n agenticseek --replicas=5

# 7. 롤아웃 상태
kubectl rollout status deployment/agenticseek-api -n agenticseek

# 8. 롤백
kubectl rollout undo deployment/agenticseek-api -n agenticseek
```

---

## 6. 모니터링 및 로깅

### 6.1 Prometheus + Grafana

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - agenticseek-network

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    ports:
      - "3000:3000"
    networks:
      - agenticseek-network

volumes:
  prometheus-data:
  grafana-data:
```

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'agenticseek'
    static_configs:
      - targets: ['api:7777']
    metrics_path: '/metrics'
```

### 6.2 ELK Stack 로깅

```yaml
# docker-compose.logging.yml
version: '3.8'

services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.10.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - es-data:/usr/share/elasticsearch/data

  logstash:
    image: docker.elastic.co/logstash/logstash:8.10.0
    volumes:
      - ./logging/logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    ports:
      - "5000:5000"
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.10.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    depends_on:
      - elasticsearch

volumes:
  es-data:
```

---

## 7. 문제 해결

### 7.1 컨테이너가 시작되지 않음

```bash
# 로그 확인
docker logs agenticseek-api

# 일반적인 문제:
# 1. .env 파일 누락
docker cp .env agenticseek-api:/app/.env

# 2. 포트 충돌
docker ps | grep 7777
lsof -i :7777

# 3. 권한 문제
docker exec agenticseek-api ls -la /app/.env
```

### 7.2 헬스체크 실패

```bash
# 컨테이너 내부 접속
docker exec -it agenticseek-api bash

# 헬스체크 수동 테스트
curl http://localhost:7777/health

# Python 프로세스 확인
ps aux | grep python
```

### 7.3 높은 메모리 사용량

```bash
# 리소스 사용량 확인
docker stats agenticseek-api

# 메모리 제한 설정
docker update --memory="2g" --memory-swap="2g" agenticseek-api

# 재시작
docker restart agenticseek-api
```

### 7.4 네트워크 문제

```bash
# 네트워크 확인
docker network ls
docker network inspect agenticseek-network

# 컨테이너 간 연결 테스트
docker exec agenticseek-api ping redis
docker exec agenticseek-api curl http://ollama:11434/api/tags
```

---

## 부록: 유용한 명령어

```bash
# === 이미지 관리 ===
docker images
docker rmi agenticseek:old-version
docker image prune -a  # 사용하지 않는 이미지 삭제

# === 컨테이너 관리 ===
docker ps -a
docker rm agenticseek-api
docker container prune  # 중지된 컨테이너 삭제

# === 로그 ===
docker logs -f --tail 100 agenticseek-api
docker logs --since 1h agenticseek-api

# === 리소스 모니터링 ===
docker stats
docker system df  # 디스크 사용량

# === 백업 ===
docker exec agenticseek-api tar czf - /app/conversations > backup.tar.gz

# === 복구 ===
docker cp backup.tar.gz agenticseek-api:/tmp/
docker exec agenticseek-api tar xzf /tmp/backup.tar.gz -C /app/

# === 클린업 ===
docker system prune -a --volumes  # 모든 사용하지 않는 리소스 삭제
```

---

**문서 버전**: 1.0
**최종 수정**: 2025-11-02
**작성자**: DevOps Team
