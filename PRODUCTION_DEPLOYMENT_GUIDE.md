# AgenticSeek 프로덕션 배포 가이드

## 📋 목차

1. [배포 전 체크리스트](#1-배포-전-체크리스트)
2. [환경 준비](#2-환경-준비)
3. [보안 설정](#3-보안-설정)
4. [배포 단계](#4-배포-단계)
5. [배포 후 검증](#5-배포-후-검증)
6. [모니터링 설정](#6-모니터링-설정)
7. [백업 및 복구](#7-백업-및-복구)
8. [문제 해결](#8-문제-해결)

---

## 1. 배포 전 체크리스트

### 필수 요구사항
- [ ] 보안 코드 리뷰 완료 (`SECURITY_REVIEW_KR.md` 검토)
- [ ] 개발 환경에서 모든 패치 테스트 완료
- [ ] 침투 테스트 통과
- [ ] 백업 계획 수립
- [ ] 롤백 계획 수립
- [ ] 팀 교육 완료

### 인프라 요구사항
- [ ] 서버: Ubuntu 20.04+ 또는 CentOS 8+
- [ ] Python 3.10+
- [ ] 메모리: 최소 8GB (권장 16GB)
- [ ] 디스크: 최소 50GB
- [ ] 네트워크: HTTPS 지원, 방화벽 설정

### 보안 요구사항
- [ ] SSL/TLS 인증서 준비
- [ ] API 키 생성
- [ ] 비밀 관리 시스템 설정 (Vault 등)
- [ ] 방화벽 규칙 정의
- [ ] 모니터링 시스템 준비

---

## 2. 환경 준비

### 2.1 서버 설정

```bash
# 시스템 업데이트
sudo apt-get update && sudo apt-get upgrade -y

# 필수 패키지 설치
sudo apt-get install -y python3.10 python3-pip python3-venv \
    git nginx certbot python3-certbot-nginx \
    redis-server ufw

# Python 가상환경 생성
python3 -m venv /opt/agenticseek/venv
source /opt/agenticseek/venv/bin/activate

# 프로젝트 클론
cd /opt/agenticseek
git clone https://github.com/Photometry4040/agenticSeek.git
cd agenticSeek

# 의존성 설치
pip install -r requirements.txt
pip install RestrictedPython  # 코드 샌드박스
```

### 2.2 SSL/TLS 인증서 설정

```bash
# Certbot으로 Let's Encrypt 인증서 발급
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 인증서 자동 갱신 설정
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### 2.3 방화벽 설정

```bash
# UFW 방화벽 설정
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH 허용 (주의: 먼저 설정!)
sudo ufw allow from 10.0.0.0/8 to any port 22 proto tcp

# HTTPS만 허용
sudo ufw allow 443/tcp

# Redis (내부 네트워크만)
sudo ufw allow from 10.0.0.0/8 to any port 6379 proto tcp

# 활성화
sudo ufw enable
sudo ufw status verbose
```

---

## 3. 보안 설정

### 3.1 API 키 생성

```bash
# 프로덕션용 API 키 생성 (3개)
cd /opt/agenticseek/agenticSeek
python security/tools/generate_api_keys.py --count 3 --export --guide

# 생성된 키를 안전하게 보관
# - API_KEY_GUIDE.txt 파일 확인
# - .env 파일에 저장 (권한 600)
chmod 600 .env
```

### 3.2 환경변수 설정

```bash
# .env 파일 편집
cat > .env << 'EOF'
# === 프로덕션 환경변수 ===

# API 인증
AGENTICSEEK_API_KEYS="key-1,key-2,key-3"

# CORS 설정
ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"

# LLM API 키 (Vault에서 로드 권장)
OPENAI_API_KEY="sk-..."
DEEPSEEK_API_KEY="..."

# 서버 설정
BACKEND_PORT=7777
REDIS_BASE_URL="redis://localhost:6379/0"

# 모니터링 및 알림
ALERT_EMAIL_ENABLED=true
ALERT_SMTP_SERVER=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_FROM_EMAIL=security@company.com
ALERT_TO_EMAILS=admin@company.com
ALERT_EMAIL_PASSWORD="app-password"

ALERT_SLACK_ENABLED=true
ALERT_SLACK_WEBHOOK="https://hooks.slack.com/services/..."

# 임계값
ALERT_AUTH_FAILURES_THRESHOLD=5
ALERT_RATE_LIMIT_THRESHOLD=10

# 기타
ENABLE_DOCS=false  # 프로덕션에서는 false
EOF

# 권한 설정
chmod 600 .env
chown www-data:www-data .env
```

### 3.3 Nginx 리버스 프록시 설정

```bash
# Nginx 설정
sudo nano /etc/nginx/sites-available/agenticseek

# 설정 내용:
```

```nginx
# /etc/nginx/sites-available/agenticseek

upstream agenticseek_backend {
    server 127.0.0.1:7777;
}

# HTTP -> HTTPS 리다이렉트
server {
    listen 80;
    server_name app.company.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS
server {
    listen 443 ssl http2;
    server_name app.company.com;

    # SSL 인증서
    ssl_certificate /etc/letsencrypt/live/app.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.company.com/privkey.pem;

    # SSL 보안 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 보안 헤더
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 최대 요청 크기
    client_max_body_size 10M;

    # 프록시 설정
    location / {
        proxy_pass http://agenticseek_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 타임아웃
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 헬스체크 엔드포인트
    location /health {
        proxy_pass http://agenticseek_backend/health;
        access_log off;
    }

    # 로깅
    access_log /var/log/nginx/agenticseek_access.log;
    error_log /var/log/nginx/agenticseek_error.log;
}
```

```bash
# 설정 활성화
sudo ln -s /etc/nginx/sites-available/agenticseek /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3.4 Systemd 서비스 설정

```bash
# Systemd 서비스 파일 생성
sudo nano /etc/systemd/system/agenticseek.service
```

```ini
[Unit]
Description=AgenticSeek Secure API
After=network.target redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/agenticseek/agenticSeek
Environment="PATH=/opt/agenticseek/venv/bin:/usr/local/bin:/usr/bin:/bin"

# 환경변수 파일
EnvironmentFile=/opt/agenticseek/agenticSeek/.env

# 실행 명령
ExecStart=/opt/agenticseek/venv/bin/python api_secure.py

# 재시작 정책
Restart=always
RestartSec=10

# 보안 설정
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/agenticseek/agenticSeek/.logs
ReadWritePaths=/opt/agenticseek/agenticSeek/conversations
ReadWritePaths=/opt/agenticseek/agenticSeek/.screenshots

# 로깅
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agenticseek

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화
sudo systemctl daemon-reload
sudo systemctl enable agenticseek.service
```

---

## 4. 배포 단계

### 4.1 자동 배포 스크립트 사용

```bash
cd /opt/agenticseek/agenticSeek
sudo ./security/deploy/deploy_secure.sh --production
```

스크립트가 자동으로:
1. ✅ 환경 검증
2. ✅ API 키 확인/생성
3. ✅ 보안 스캔
4. ✅ 침투 테스트 (선택)
5. ✅ 백업 생성
6. ✅ 서비스 설정

### 4.2 수동 배포

**Step 1: 보안 스캔**
```bash
python security/quick_scan.py
```

**Step 2: API 시작**
```bash
sudo systemctl start agenticseek
```

**Step 3: 상태 확인**
```bash
sudo systemctl status agenticseek
```

**Step 4: 로그 확인**
```bash
sudo journalctl -u agenticseek -f
```

---

## 5. 배포 후 검증

### 5.1 헬스체크

```bash
# 1. 기본 헬스체크
curl https://app.company.com/health

# 예상 결과:
# {
#   "status": "healthy",
#   "version": "1.0.0-secure",
#   "security": "enabled",
#   "timestamp": 1234567890.123
# }
```

### 5.2 인증 테스트

```bash
# 2. 인증 없이 접근 (차단되어야 함)
curl -X POST https://app.company.com/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# 예상 결과:
# {"detail": "Missing API Key"}  (HTTP 403)

# 3. 올바른 API 키로 접근 (허용되어야 함)
curl -X POST https://app.company.com/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"query": "What is 2+2?", "tts_enabled": false}'

# 예상 결과:
# {"done": "true", "answer": "...", ...}  (HTTP 200)
```

### 5.3 CORS 테스트

```bash
# 4. 허용되지 않은 origin (차단되어야 함)
curl -H "Origin: http://evil.com" \
  -I https://app.company.com/health

# Access-Control-Allow-Origin이 없어야 함

# 5. 허용된 origin (허용되어야 함)
curl -H "Origin: https://app.company.com" \
  -I https://app.company.com/health

# Access-Control-Allow-Origin: https://app.company.com
```

### 5.4 침투 테스트

```bash
cd security/pentest
./automated_pentest.sh https://app.company.com
```

**통과 기준**:
- ✅ No authentication: SAFE
- ✅ CORS misconfiguration: SAFE
- ✅ Rate limiting: SAFE
- ✅ 0 CRITICAL vulnerabilities

---

## 6. 모니터링 설정

### 6.1 로그 모니터링

```bash
# 실시간 로그
tail -f .logs/backend_secure.log
tail -f .logs/security_events.log
tail -f /var/log/nginx/agenticseek_access.log

# 에러만 필터링
tail -f .logs/backend_secure.log | grep ERROR
```

### 6.2 알림 설정 테스트

```bash
# 알림 테스트
python security/monitoring/alert_config.py
```

### 6.3 메트릭 수집 (Optional - Prometheus)

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'agenticseek'
    static_configs:
      - targets: ['localhost:7777']
    metrics_path: '/metrics'
```

---

## 7. 백업 및 복구

### 7.1 자동 백업 스크립트

```bash
# /opt/agenticseek/backup.sh
#!/bin/bash

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/agenticseek/$DATE"
PROJECT_DIR="/opt/agenticseek/agenticSeek"

mkdir -p "$BACKUP_DIR"

# 대화 내역 백업
tar -czf "$BACKUP_DIR/conversations.tar.gz" \
  -C "$PROJECT_DIR" conversations/

# 설정 백업
cp "$PROJECT_DIR/.env" "$BACKUP_DIR/.env"
cp "$PROJECT_DIR/config.ini" "$BACKUP_DIR/config.ini"

# 로그 백업
tar -czf "$BACKUP_DIR/logs.tar.gz" \
  -C "$PROJECT_DIR" .logs/

# 암호화
ENCRYPT_KEY=$(cat /secure/backup.key)
openssl enc -aes-256-cbc -salt \
  -in "$BACKUP_DIR/conversations.tar.gz" \
  -out "$BACKUP_DIR/conversations.tar.gz.enc" \
  -pass pass:$ENCRYPT_KEY

# 오프사이트 전송 (S3)
aws s3 cp "$BACKUP_DIR" \
  s3://company-backup/agenticseek/$DATE/ \
  --recursive

# 로컬 정리 (30일 이상)
find /backup/agenticseek -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR"
```

```bash
# 실행 권한
chmod +x /opt/agenticseek/backup.sh

# Cron 설정 (매일 자정)
crontab -e
# 추가:
0 0 * * * /opt/agenticseek/backup.sh >> /var/log/agenticseek-backup.log 2>&1
```

### 7.2 복구 절차

```bash
# 1. 서비스 중지
sudo systemctl stop agenticseek

# 2. 백업에서 복구
RESTORE_DATE="20250101_000000"
aws s3 cp s3://company-backup/agenticseek/$RESTORE_DATE/ \
  /tmp/restore/ --recursive

# 3. 암호 해제
openssl enc -aes-256-cbc -d \
  -in /tmp/restore/conversations.tar.gz.enc \
  -out /tmp/restore/conversations.tar.gz \
  -pass pass:$(cat /secure/backup.key)

# 4. 압축 해제
tar -xzf /tmp/restore/conversations.tar.gz \
  -C /opt/agenticseek/agenticSeek/

# 5. 권한 복구
chown -R www-data:www-data /opt/agenticseek/agenticSeek/conversations

# 6. 서비스 재시작
sudo systemctl start agenticseek
```

---

## 8. 문제 해결

### 8.1 서비스가 시작되지 않음

```bash
# 로그 확인
sudo journalctl -u agenticseek -n 100 --no-pager

# 일반적인 원인:
# 1. .env 파일 권한
sudo chown www-data:www-data /opt/agenticseek/agenticSeek/.env

# 2. Python 가상환경
source /opt/agenticseek/venv/bin/activate
which python  # /opt/agenticseek/venv/bin/python 확인

# 3. 포트 충돌
sudo lsof -i :7777
```

### 8.2 인증 실패

```bash
# API 키 확인
grep AGENTICSEEK_API_KEYS /opt/agenticseek/agenticSeek/.env

# 키 재생성
python security/tools/generate_api_keys.py --count 3 --export

# 서비스 재시작
sudo systemctl restart agenticseek
```

### 8.3 높은 메모리 사용량

```bash
# 메모리 사용량 확인
ps aux | grep python

# 서비스 재시작
sudo systemctl restart agenticseek

# 영구적 해결: config.ini에서 메모리 제한 설정
```

### 8.4 느린 응답 시간

```bash
# Nginx 로그 분석
tail -f /var/log/nginx/agenticseek_access.log

# LLM 제공자 확인
curl -X GET "http://localhost:11434/api/tags"  # Ollama

# Redis 확인
redis-cli ping
```

---

## 9. 유지보수 체크리스트

### 일일
- [ ] 로그 검토 (에러, 경고)
- [ ] 디스크 공간 확인
- [ ] 응답 시간 모니터링

### 주간
- [ ] 보안 알림 검토
- [ ] 백업 검증
- [ ] 성능 메트릭 분석

### 월간
- [ ] 의존성 업데이트 검토
- [ ] 보안 패치 적용
- [ ] API 키 로테이션 검토

### 분기별
- [ ] 침투 테스트 실행
- [ ] 보안 정책 검토
- [ ] API 키 로테이션 (90일)
- [ ] 전체 시스템 백업

---

## 10. 긴급 연락처

| 역할 | 이름 | 연락처 | 가용 시간 |
|------|------|--------|-----------|
| 보안 책임자 | [이름] | [전화] | 24/7 |
| 시스템 관리자 | [이름] | [전화] | 평일 9-18시 |
| DevOps | [이름] | [전화] | 평일 9-18시 |

---

## 부록 A: 명령어 빠른 참조

```bash
# 서비스 관리
sudo systemctl start agenticseek
sudo systemctl stop agenticseek
sudo systemctl restart agenticseek
sudo systemctl status agenticseek

# 로그 확인
sudo journalctl -u agenticseek -f
tail -f .logs/backend_secure.log

# 백업
/opt/agenticseek/backup.sh

# API 키 생성
python security/tools/generate_api_keys.py --count 3

# 보안 스캔
python security/quick_scan.py

# 침투 테스트
./security/pentest/automated_pentest.sh https://app.company.com
```

---

**문서 버전**: 1.0
**최종 수정**: 2025-11-01
**작성자**: Security Team
