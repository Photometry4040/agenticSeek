# AgenticSeek 고가용성(HA) 및 로드밸런싱 가이드

## 📋 목차

1. [고가용성 아키텍처 개요](#1-고가용성-아키텍처-개요)
2. [로드밸런서 설정](#2-로드밸런서-설정)
3. [다중 인스턴스 구성](#3-다중-인스턴스-구성)
4. [데이터베이스 HA](#4-데이터베이스-ha)
5. [세션 관리 및 상태 동기화](#5-세션-관리-및-상태-동기화)
6. [장애 복구 및 페일오버](#6-장애-복구-및-페일오버)
7. [모니터링 및 헬스체크](#7-모니터링-및-헬스체크)
8. [재해 복구(DR)](#8-재해-복구dr)

---

## 1. 고가용성 아키텍처 개요

### 1.1 HA 아키텍처 다이어그램

```
                    ┌─────────────────┐
                    │   CloudFlare    │
                    │   (Global CDN)  │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  AWS Route 53   │
                    │  (DNS Failover) │
                    └────────┬────────┘
                             │
           ┌─────────────────┴─────────────────┐
           │                                   │
    ┌──────┴──────┐                    ┌──────┴──────┐
    │  Region 1   │                    │  Region 2   │
    │  (Primary)  │                    │ (Secondary) │
    └──────┬──────┘                    └──────┬──────┘
           │                                   │
    ┌──────┴──────┐                    ┌──────┴──────┐
    │     ALB     │                    │     ALB     │
    │ (us-east-1) │                    │ (us-west-2) │
    └──────┬──────┘                    └──────┬──────┘
           │                                   │
    ┌──────┴──────────────┐           ┌───────┴──────────────┐
    │                     │           │                      │
┌───┴───┐  ┌───┴───┐  ┌───┴───┐   ┌───┴───┐  ┌───┴───┐  ┌───┴───┐
│ API 1 │  │ API 2 │  │ API 3 │   │ API 4 │  │ API 5 │  │ API 6 │
│ (AZ-a)│  │ (AZ-b)│  │ (AZ-c)│   │ (AZ-a)│  │ (AZ-b)│  │ (AZ-c)│
└───┬───┘  └───┬───┘  └───┬───┘   └───┬───┘  └───┬───┘  └───┬───┘
    │          │          │           │          │          │
    └──────────┴──────────┴───────────┴──────────┴──────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         ┌────┴────┐          ┌────┴────┐
         │ Redis   │          │  RDS    │
         │ Cluster │          │ Multi-AZ│
         │(Sentinel)│         │(Primary)│
         └─────────┘          └────┬────┘
                                   │
                             ┌─────┴─────┐
                             │    RDS    │
                             │  (Standby)│
                             └───────────┘
```

### 1.2 SLA 목표

| 메트릭 | 목표 | 측정 방법 |
|--------|------|-----------|
| **가용성** | 99.95% (연간 다운타임 < 4.38시간) | Uptime 모니터링 |
| **복구 시간 목표 (RTO)** | < 5분 | 자동 페일오버 |
| **복구 시점 목표 (RPO)** | < 1분 | 데이터 복제 지연 |
| **평균 복구 시간 (MTTR)** | < 15분 | 인시던트 로그 |
| **평균 장애 간격 (MTBF)** | > 30일 | 장애 추적 |

### 1.3 HA 구성 요소

- ✅ **다중 가용 영역 (Multi-AZ)**: 3개 이상의 AZ에 인스턴스 분산
- ✅ **로드 밸런서**: Application Load Balancer (ALB) 또는 Nginx
- ✅ **자동 확장**: Auto Scaling Group (ASG)
- ✅ **데이터베이스 복제**: Redis Sentinel, RDS Multi-AZ
- ✅ **헬스체크**: 주기적인 상태 확인 및 자동 복구
- ✅ **백업 및 복구**: 자동 백업, 지리적 복제

---

## 2. 로드밸런서 설정

### 2.1 AWS Application Load Balancer (ALB)

```bash
# AWS CLI로 ALB 생성

# 1. 보안 그룹 생성
aws ec2 create-security-group \
    --group-name agenticseek-alb-sg \
    --description "Security group for AgenticSeek ALB" \
    --vpc-id vpc-12345678

aws ec2 authorize-security-group-ingress \
    --group-id sg-12345678 \
    --protocol tcp \
    --port 443 \
    --cidr 0.0.0.0/0

# 2. ALB 생성
aws elbv2 create-load-balancer \
    --name agenticseek-alb \
    --subnets subnet-12345678 subnet-87654321 subnet-11111111 \
    --security-groups sg-12345678 \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4

# 3. 타겟 그룹 생성
aws elbv2 create-target-group \
    --name agenticseek-tg \
    --protocol HTTP \
    --port 7777 \
    --vpc-id vpc-12345678 \
    --health-check-enabled \
    --health-check-protocol HTTP \
    --health-check-path /health \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --matcher HttpCode=200

# 4. 리스너 생성 (HTTPS)
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:... \
    --protocol HTTPS \
    --port 443 \
    --certificates CertificateArn=arn:aws:acm:... \
    --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...

# 5. HTTP -> HTTPS 리다이렉트
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:... \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=redirect,RedirectConfig="{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}"
```

### 2.2 Nginx 로드 밸런서

```nginx
# /etc/nginx/nginx.conf

upstream agenticseek_backend {
    # 로드 밸런싱 알고리즘
    least_conn;  # 최소 연결 수 기반
    # ip_hash;   # 클라이언트 IP 기반 (세션 고정)
    # random;    # 랜덤

    # 백엔드 서버들
    server 10.0.1.10:7777 max_fails=3 fail_timeout=30s weight=3;
    server 10.0.1.11:7777 max_fails=3 fail_timeout=30s weight=3;
    server 10.0.1.12:7777 max_fails=3 fail_timeout=30s weight=3;
    server 10.0.2.10:7777 max_fails=3 fail_timeout=30s weight=2 backup;  # 백업 서버

    # 연결 풀링
    keepalive 32;
    keepalive_requests 100;
    keepalive_timeout 60s;
}

server {
    listen 443 ssl http2;
    server_name app.company.com;

    # SSL 설정
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 로드 밸런싱 설정
    location / {
        proxy_pass http://agenticseek_backend;

        # 헤더 설정
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 연결 설정
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # 타임아웃
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # 재시도 설정
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
        proxy_next_upstream_tries 3;
        proxy_next_upstream_timeout 10s;
    }

    # 헬스체크 (로드 밸런서용)
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### 2.3 HAProxy 설정

```conf
# /etc/haproxy/haproxy.cfg

global
    log /dev/log local0
    log /dev/log local1 notice
    maxconn 4096
    user haproxy
    group haproxy
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    option http-server-close
    option redispatch
    retries 3
    timeout connect 5000
    timeout client 50000
    timeout server 50000

# 프론트엔드
frontend agenticseek_frontend
    bind *:443 ssl crt /etc/ssl/certs/agenticseek.pem
    bind *:80
    redirect scheme https code 301 if !{ ssl_fc }

    # ACL 정의
    acl is_health path /health
    acl is_api path_beg /query /api

    # 헬스체크는 로그 안 남김
    http-request set-log-level silent if is_health

    default_backend agenticseek_backend

# 백엔드
backend agenticseek_backend
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200

    # 서버 정의
    server api1 10.0.1.10:7777 check inter 10s fall 3 rise 2 weight 100
    server api2 10.0.1.11:7777 check inter 10s fall 3 rise 2 weight 100
    server api3 10.0.1.12:7777 check inter 10s fall 3 rise 2 weight 100
    server api4 10.0.2.10:7777 check inter 10s fall 3 rise 2 weight 50 backup

# 통계 페이지
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats auth admin:password
```

---

## 3. 다중 인스턴스 구성

### 3.1 AWS Auto Scaling Group

```bash
# 1. Launch Template 생성
aws ec2 create-launch-template \
    --launch-template-name agenticseek-lt \
    --version-description "v1.0" \
    --launch-template-data '{
        "ImageId": "ami-12345678",
        "InstanceType": "t3.large",
        "KeyName": "agenticseek-key",
        "SecurityGroupIds": ["sg-12345678"],
        "UserData": "'"$(base64 -w 0 user-data.sh)"'",
        "IamInstanceProfile": {
            "Arn": "arn:aws:iam::123456789012:instance-profile/agenticseek-role"
        },
        "TagSpecifications": [{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": "AgenticSeek-API"},
                {"Key": "Environment", "Value": "production"}
            ]
        }]
    }'

# 2. Auto Scaling Group 생성
aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name agenticseek-asg \
    --launch-template "LaunchTemplateName=agenticseek-lt,Version=\$Latest" \
    --min-size 3 \
    --max-size 10 \
    --desired-capacity 3 \
    --default-cooldown 300 \
    --health-check-type ELB \
    --health-check-grace-period 300 \
    --vpc-zone-identifier "subnet-12345678,subnet-87654321,subnet-11111111" \
    --target-group-arns "arn:aws:elasticloadbalancing:..."

# 3. 스케일링 정책 생성 (CPU 기반)
aws autoscaling put-scaling-policy \
    --auto-scaling-group-name agenticseek-asg \
    --policy-name scale-up \
    --policy-type TargetTrackingScaling \
    --target-tracking-configuration '{
        "PredefinedMetricSpecification": {
            "PredefinedMetricType": "ASGAverageCPUUtilization"
        },
        "TargetValue": 70.0
    }'

# 4. 스케줄 기반 스케일링 (예: 업무 시간)
aws autoscaling put-scheduled-action \
    --auto-scaling-group-name agenticseek-asg \
    --scheduled-action-name scale-up-morning \
    --recurrence "0 8 * * MON-FRI" \
    --min-size 5 \
    --max-size 15 \
    --desired-capacity 5

aws autoscaling put-scheduled-action \
    --auto-scaling-group-name agenticseek-asg \
    --scheduled-action-name scale-down-evening \
    --recurrence "0 18 * * MON-FRI" \
    --min-size 3 \
    --max-size 10 \
    --desired-capacity 3
```

### 3.2 User Data 스크립트

```bash
#!/bin/bash
# user-data.sh - EC2 인스턴스 부트스트랩

set -e

# 로그 설정
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=== AgenticSeek Instance Bootstrap ==="

# 1. 시스템 업데이트
apt-get update
apt-get upgrade -y

# 2. Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable docker
systemctl start docker

# 3. AWS CLI 설치
apt-get install -y awscli

# 4. 환경변수 가져오기 (AWS Secrets Manager)
REGION=$(ec2-metadata --availability-zone | sed 's/placement: \(.*\).$/\1/')
SECRET_ID="agenticseek/production/env"

aws secretsmanager get-secret-value \
    --secret-id $SECRET_ID \
    --region $REGION \
    --query SecretString \
    --output text > /opt/agenticseek/.env

# 5. Docker Compose 다운로드
curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# 6. 애플리케이션 배포
cd /opt/agenticseek
docker-compose pull
docker-compose up -d

# 7. CloudWatch 에이전트 설치
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i -E ./amazon-cloudwatch-agent.deb

# CloudWatch 설정
cat > /opt/aws/amazon-cloudwatch-agent/etc/config.json << 'EOF'
{
  "metrics": {
    "namespace": "AgenticSeek",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          {"name": "cpu_usage_idle", "rename": "CPU_IDLE", "unit": "Percent"}
        ],
        "totalcpu": false
      },
      "mem": {
        "measurement": [
          {"name": "mem_used_percent", "rename": "MEMORY_USED", "unit": "Percent"}
        ]
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/opt/agenticseek/logs/*.log",
            "log_group_name": "/aws/ec2/agenticseek",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json

echo "=== Bootstrap completed ==="
```

### 3.3 Kubernetes Horizontal Pod Autoscaler (HPA)

```yaml
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
  maxReplicas: 20
  metrics:
  # CPU 기반 스케일링
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  # 메모리 기반 스케일링
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  # 커스텀 메트릭 (요청 수)
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "1000"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300  # 5분 대기
      policies:
      - type: Percent
        value: 50  # 한 번에 50%까지 축소
        periodSeconds: 60
      - type: Pods
        value: 2  # 한 번에 2개까지 축소
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0  # 즉시 확장
      policies:
      - type: Percent
        value: 100  # 한 번에 100%까지 확장
        periodSeconds: 15
      - type: Pods
        value: 4  # 한 번에 4개까지 확장
        periodSeconds: 15
```

---

## 4. 데이터베이스 HA

### 4.1 Redis Sentinel (고가용성)

```bash
# Redis Sentinel 설정

# 1. Redis Master 설정 (redis-master.conf)
cat > /etc/redis/redis-master.conf << EOF
port 6379
bind 0.0.0.0
requirepass strongpassword
masterauth strongpassword

# 지속성
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfilename "appendonly.aof"

# 복제
min-replicas-to-write 1
min-replicas-max-lag 10
EOF

# 2. Redis Replica 설정 (redis-replica.conf)
cat > /etc/redis/redis-replica.conf << EOF
port 6379
bind 0.0.0.0
requirepass strongpassword
masterauth strongpassword

# Master 연결
replicaof redis-master 6379
replica-read-only yes
EOF

# 3. Sentinel 설정 (sentinel.conf)
cat > /etc/redis/sentinel.conf << EOF
port 26379
bind 0.0.0.0

# Master 모니터링
sentinel monitor mymaster redis-master 6379 2
sentinel auth-pass mymaster strongpassword
sentinel down-after-milliseconds mymaster 5000
sentinel parallel-syncs mymaster 1
sentinel failover-timeout mymaster 10000

# 알림
sentinel notification-script mymaster /etc/redis/notify.sh
sentinel client-reconfig-script mymaster /etc/redis/reconfig.sh
EOF

# 4. Sentinel 시작
redis-sentinel /etc/redis/sentinel.conf
```

### 4.2 PostgreSQL HA (Patroni)

```yaml
# patroni.yml

scope: agenticseek
name: postgres1

restapi:
  listen: 0.0.0.0:8008
  connect_address: 10.0.1.10:8008

etcd:
  hosts: 10.0.1.20:2379,10.0.1.21:2379,10.0.1.22:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      parameters:
        max_connections: 200
        shared_buffers: 256MB
        effective_cache_size: 1GB
        maintenance_work_mem: 64MB
        checkpoint_completion_target: 0.9
        wal_buffers: 16MB
        default_statistics_target: 100
        random_page_cost: 1.1
        effective_io_concurrency: 200
        work_mem: 6553kB
        min_wal_size: 1GB
        max_wal_size: 4GB

  initdb:
    - encoding: UTF8
    - data-checksums

postgresql:
  listen: 0.0.0.0:5432
  connect_address: 10.0.1.10:5432
  data_dir: /var/lib/postgresql/14/main
  bin_dir: /usr/lib/postgresql/14/bin
  authentication:
    replication:
      username: replicator
      password: reppassword
    superuser:
      username: postgres
      password: postgrespassword

tags:
    nofailover: false
    noloadbalance: false
    clonefrom: false
    nosync: false
```

### 4.3 AWS RDS Multi-AZ

```bash
# RDS Multi-AZ 설정 (Terraform)

resource "aws_db_instance" "agenticseek_db" {
  identifier = "agenticseek-db"

  # 엔진 설정
  engine               = "postgres"
  engine_version       = "14.7"
  instance_class       = "db.r6g.xlarge"
  allocated_storage    = 100
  storage_type         = "gp3"
  storage_encrypted    = true

  # HA 설정
  multi_az             = true  # Multi-AZ 활성화

  # 백업 설정
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  # 네트워크
  db_subnet_group_name   = aws_db_subnet_group.agenticseek.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # 모니터링
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  monitoring_interval    = 60
  monitoring_role_arn    = aws_iam_role.rds_monitoring.arn

  # 성능
  performance_insights_enabled = true

  # 자동 minor 버전 업그레이드
  auto_minor_version_upgrade = true

  tags = {
    Name        = "AgenticSeek DB"
    Environment = "production"
  }
}

# Read Replica 생성
resource "aws_db_instance" "agenticseek_db_replica" {
  identifier             = "agenticseek-db-replica"
  replicate_source_db    = aws_db_instance.agenticseek_db.identifier
  instance_class         = "db.r6g.large"
  publicly_accessible    = false
  skip_final_snapshot    = true

  tags = {
    Name        = "AgenticSeek DB Replica"
    Environment = "production"
  }
}
```

---

## 5. 세션 관리 및 상태 동기화

### 5.1 Stateless 아키텍처

```python
# session_manager.py

from typing import Optional
import redis
import json
import hashlib
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.session_ttl = 3600  # 1시간

    def create_session(self, user_id: str, data: dict) -> str:
        # 세션 ID 생성
        session_id = hashlib.sha256(
            f"{user_id}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()

        # Redis에 저장 (자동 만료)
        session_key = f"session:{session_id}"
        self.redis.setex(
            session_key,
            self.session_ttl,
            json.dumps({
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                **data
            })
        )

        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        session_key = f"session:{session_id}"
        data = self.redis.get(session_key)

        if data:
            # TTL 갱신
            self.redis.expire(session_key, self.session_ttl)
            return json.loads(data)

        return None

    def delete_session(self, session_id: str):
        session_key = f"session:{session_id}"
        self.redis.delete(session_key)

# FastAPI 통합
from fastapi import FastAPI, Depends, HTTPException, Cookie

app = FastAPI()

async def get_current_session(
    session_id: Optional[str] = Cookie(None)
) -> dict:
    if not session_id:
        raise HTTPException(status_code=401, detail="No session")

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    return session

@app.post("/query")
async def query(
    request: dict,
    session: dict = Depends(get_current_session)
):
    # 세션 정보 사용
    user_id = session["user_id"]
    # ... 처리 로직
```

### 5.2 Sticky Session (세션 고정)

```nginx
# Nginx - IP Hash 기반 세션 고정

upstream agenticseek_backend {
    ip_hash;  # 클라이언트 IP 기반 라우팅

    server 10.0.1.10:7777;
    server 10.0.1.11:7777;
    server 10.0.1.12:7777;
}

# 또는 쿠키 기반 세션 고정
upstream agenticseek_backend {
    hash $cookie_session_id consistent;

    server 10.0.1.10:7777;
    server 10.0.1.11:7777;
    server 10.0.1.12:7777;
}
```

### 5.3 분산 캐시 동기화

```python
# distributed_cache.py

from redis import Redis
from redis.sentinel import Sentinel
from typing import Optional, List

class DistributedCache:
    def __init__(self, sentinel_hosts: List[tuple]):
        # Sentinel을 통한 Redis 클러스터 연결
        self.sentinel = Sentinel(
            sentinel_hosts,
            socket_timeout=0.5,
            sentinel_kwargs={'password': 'sentinelpass'}
        )

        # Master (쓰기용)
        self.master = self.sentinel.master_for(
            'mymaster',
            socket_timeout=0.5,
            password='redispass',
            decode_responses=True
        )

        # Slave (읽기용)
        self.slave = self.sentinel.slave_for(
            'mymaster',
            socket_timeout=0.5,
            password='redispass',
            decode_responses=True
        )

    def set(self, key: str, value: str, ttl: int = 3600):
        # Master에 쓰기
        self.master.setex(key, ttl, value)

    def get(self, key: str) -> Optional[str]:
        # Slave에서 읽기 (부하 분산)
        try:
            return self.slave.get(key)
        except:
            # Slave 실패시 Master에서 읽기
            return self.master.get(key)

    def delete(self, key: str):
        self.master.delete(key)

    def get_master_info(self) -> dict:
        # Master 정보 조회
        master_addr = self.sentinel.discover_master('mymaster')
        return {
            "host": master_addr[0],
            "port": master_addr[1]
        }

    def get_slaves_info(self) -> List[dict]:
        # Slave 정보 조회
        slaves = self.sentinel.discover_slaves('mymaster')
        return [
            {"host": slave[0], "port": slave[1]}
            for slave in slaves
        ]
```

---

## 6. 장애 복구 및 페일오버

### 6.1 자동 페일오버 시나리오

```python
# failover_handler.py

import time
import requests
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class FailoverHandler:
    def __init__(self, backend_servers: List[str]):
        self.servers = backend_servers
        self.active_servers = set(backend_servers)
        self.health_check_interval = 10  # 10초

    def health_check(self, server: str) -> bool:
        try:
            response = requests.get(
                f"{server}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

    def monitor_loop(self):
        while True:
            for server in self.servers:
                is_healthy = self.health_check(server)

                if is_healthy and server not in self.active_servers:
                    # 서버 복구됨
                    logger.info(f"✅ Server recovered: {server}")
                    self.active_servers.add(server)
                    self.notify_load_balancer("add", server)

                elif not is_healthy and server in self.active_servers:
                    # 서버 장애 발생
                    logger.error(f"❌ Server failed: {server}")
                    self.active_servers.remove(server)
                    self.notify_load_balancer("remove", server)

                    # 자동 복구 시도
                    self.attempt_auto_recovery(server)

            time.sleep(self.health_check_interval)

    def attempt_auto_recovery(self, server: str):
        # 서버 재시작 시도
        logger.info(f"🔄 Attempting auto-recovery for {server}")

        # AWS Auto Scaling 또는 Kubernetes를 통한 재시작
        # 예: kubectl delete pod <pod-name>
        # 예: aws autoscaling terminate-instance-in-auto-scaling-group

    def notify_load_balancer(self, action: str, server: str):
        # 로드 밸런서에 서버 추가/제거 알림
        # 예: Nginx upstream 업데이트, ALB 타겟 그룹 수정
        pass
```

### 6.2 Circuit Breaker 패턴

```python
# circuit_breaker.py

from enum import Enum
from datetime import datetime, timedelta
import asyncio

class CircuitState(Enum):
    CLOSED = "closed"      # 정상
    OPEN = "open"          # 차단 (장애)
    HALF_OPEN = "half_open"  # 복구 시도

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        success_threshold: int = 2
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            # 타임아웃 확인
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)

            # 성공 시
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0

            return result

        except Exception as e:
            # 실패 시
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

            raise e

# 사용 예제
breaker = CircuitBreaker(failure_threshold=5, timeout=60)

async def call_external_api():
    try:
        result = await breaker.call(
            external_api_request,
            url="https://api.example.com"
        )
        return result
    except Exception as e:
        # Fallback 로직
        return fallback_response()
```

---

## 7. 모니터링 및 헬스체크

### 7.1 종합 헬스체크

```python
# health_check.py

from fastapi import FastAPI, Response
from typing import Dict
import redis
import psycopg2

app = FastAPI()

async def check_redis() -> Dict:
    try:
        r = redis.Redis(host='localhost', port=6379)
        r.ping()
        return {"status": "healthy", "latency_ms": 1}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_database() -> Dict:
    try:
        conn = psycopg2.connect("dbname=agenticseek")
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_ollama() -> Dict:
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return {
            "status": "healthy" if response.status_code == 200 else "unhealthy"
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/health")
async def health_check():
    checks = {
        "api": {"status": "healthy"},
        "redis": await check_redis(),
        "database": await check_database(),
        "ollama": await check_ollama()
    }

    # 전체 상태 판단
    all_healthy = all(
        check["status"] == "healthy"
        for check in checks.values()
    )

    status_code = 200 if all_healthy else 503

    return Response(
        content=json.dumps({
            "status": "healthy" if all_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }),
        status_code=status_code,
        media_type="application/json"
    )

@app.get("/health/liveness")
async def liveness():
    # Kubernetes liveness probe
    return {"status": "alive"}

@app.get("/health/readiness")
async def readiness():
    # Kubernetes readiness probe
    redis_ok = (await check_redis())["status"] == "healthy"
    db_ok = (await check_database())["status"] == "healthy"

    if redis_ok and db_ok:
        return {"status": "ready"}
    else:
        return Response(
            content=json.dumps({"status": "not ready"}),
            status_code=503
        )
```

### 7.2 Prometheus 메트릭

```python
# prometheus_metrics.py

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import FastAPI, Response

app = FastAPI()

# 메트릭 정의
REQUEST_COUNT = Counter(
    'agenticseek_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'agenticseek_request_duration_seconds',
    'Request latency'
)

ACTIVE_CONNECTIONS = Gauge(
    'agenticseek_active_connections',
    'Active connections'
)

DB_CONNECTIONS = Gauge(
    'agenticseek_db_connections',
    'Database connections',
    ['state']  # active, idle
)

CACHE_HIT_RATE = Gauge(
    'agenticseek_cache_hit_rate',
    'Cache hit rate'
)

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

---

## 8. 재해 복구(DR)

### 8.1 백업 전략

```bash
#!/bin/bash
# backup-dr.sh - 재해 복구용 백업

set -e

BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"

# 1. 데이터베이스 백업
echo "📦 Backing up database..."
pg_dump -h primary-db.company.com -U postgres agenticseek | \
    gzip > /backup/db_${BACKUP_DATE}.sql.gz

# S3에 업로드 (Primary Region)
aws s3 cp /backup/db_${BACKUP_DATE}.sql.gz \
    s3://agenticseek-backup-${PRIMARY_REGION}/db/ \
    --storage-class STANDARD_IA

# 크로스 리전 복제 (DR Region)
aws s3 cp /backup/db_${BACKUP_DATE}.sql.gz \
    s3://agenticseek-backup-${DR_REGION}/db/ \
    --storage-class GLACIER

# 2. Redis 데이터 백업
echo "📦 Backing up Redis..."
redis-cli --rdb /backup/redis_${BACKUP_DATE}.rdb

aws s3 cp /backup/redis_${BACKUP_DATE}.rdb \
    s3://agenticseek-backup-${PRIMARY_REGION}/redis/ \
    --storage-class STANDARD_IA

# 3. 대화 내역 백업
echo "📦 Backing up conversations..."
tar -czf /backup/conversations_${BACKUP_DATE}.tar.gz \
    /opt/agenticseek/conversations/

aws s3 cp /backup/conversations_${BACKUP_DATE}.tar.gz \
    s3://agenticseek-backup-${PRIMARY_REGION}/conversations/ \
    --storage-class STANDARD_IA

# 4. 설정 파일 백업
echo "📦 Backing up configurations..."
tar -czf /backup/config_${BACKUP_DATE}.tar.gz \
    /opt/agenticseek/.env \
    /opt/agenticseek/config.ini \
    /etc/nginx/

aws s3 cp /backup/config_${BACKUP_DATE}.tar.gz \
    s3://agenticseek-backup-${PRIMARY_REGION}/config/

# 5. 오래된 백업 정리 (30일 이상)
find /backup -mtime +30 -delete

echo "✅ Backup completed: $BACKUP_DATE"
```

### 8.2 DR 복구 절차

```bash
#!/bin/bash
# restore-dr.sh - DR 사이트 복구

set -e

RESTORE_DATE=$1
DR_REGION="us-west-2"

if [ -z "$RESTORE_DATE" ]; then
    echo "Usage: ./restore-dr.sh <backup_date>"
    echo "Example: ./restore-dr.sh 20250102_120000"
    exit 1
fi

echo "🔄 Starting DR restoration from backup: $RESTORE_DATE"

# 1. S3에서 백업 다운로드
mkdir -p /restore
aws s3 cp s3://agenticseek-backup-${DR_REGION}/db/db_${RESTORE_DATE}.sql.gz \
    /restore/ --region $DR_REGION

aws s3 cp s3://agenticseek-backup-${DR_REGION}/redis/redis_${RESTORE_DATE}.rdb \
    /restore/ --region $DR_REGION

aws s3 cp s3://agenticseek-backup-${DR_REGION}/conversations/conversations_${RESTORE_DATE}.tar.gz \
    /restore/ --region $DR_REGION

# 2. 데이터베이스 복구
echo "🗄️  Restoring database..."
gunzip /restore/db_${RESTORE_DATE}.sql.gz
psql -h dr-db.company.com -U postgres -d agenticseek < /restore/db_${RESTORE_DATE}.sql

# 3. Redis 복구
echo "💾 Restoring Redis..."
sudo systemctl stop redis
sudo cp /restore/redis_${RESTORE_DATE}.rdb /var/lib/redis/dump.rdb
sudo chown redis:redis /var/lib/redis/dump.rdb
sudo systemctl start redis

# 4. 대화 내역 복구
echo "💬 Restoring conversations..."
tar -xzf /restore/conversations_${RESTORE_DATE}.tar.gz -C /

# 5. DNS 전환 (Route 53)
echo "🌐 Updating DNS to DR site..."
aws route53 change-resource-record-sets \
    --hosted-zone-id Z1234567890ABC \
    --change-batch '{
        "Changes": [{
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "app.company.com",
                "Type": "A",
                "AliasTarget": {
                    "HostedZoneId": "Z234567890BCD",
                    "DNSName": "dr-alb.company.com",
                    "EvaluateTargetHealth": true
                }
            }
        }]
    }'

# 6. 헬스체크
for i in {1..30}; do
    if curl -f https://app.company.com/health; then
        echo "✅ DR site is healthy"
        exit 0
    fi
    echo "Waiting... ($i/30)"
    sleep 10
done

echo "❌ DR site health check failed"
exit 1
```

---

## 부록: HA 체크리스트

### 인프라
- [ ] 다중 가용 영역 (3+ AZ) 구성
- [ ] 로드 밸런서 설정 및 테스트
- [ ] Auto Scaling 정책 설정
- [ ] 백업 서버 준비

### 데이터
- [ ] 데이터베이스 복제 (Multi-AZ/Replica)
- [ ] Redis Sentinel 구성
- [ ] 정기 백업 설정 (일일)
- [ ] 크로스 리전 복제

### 모니터링
- [ ] 헬스체크 엔드포인트
- [ ] Prometheus 메트릭 수집
- [ ] 알림 설정 (Slack, PagerDuty)
- [ ] 대시보드 구성

### 테스트
- [ ] 페일오버 테스트 (월간)
- [ ] DR 복구 훈련 (분기)
- [ ] 부하 테스트 (배포 전)
- [ ] 카오스 엔지니어링

---

**문서 버전**: 1.0
**최종 수정**: 2025-11-02
**작성자**: Infrastructure Team
