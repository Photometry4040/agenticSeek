# AgenticSeek 기업 보안 정책

## 문서 정보
- **버전**: 1.0
- **최종 수정일**: 2025-11-01
- **소유자**: 보안팀
- **검토 주기**: 분기별

---

## 1. 개요

### 1.1 목적
본 문서는 AgenticSeek를 기업 환경에서 안전하게 사용하기 위한 보안 정책, 절차 및 가이드라인을 정의합니다.

### 1.2 적용 범위
- AgenticSeek 시스템의 모든 인스턴스
- 시스템에 접근하는 모든 사용자
- 시스템과 통합되는 모든 애플리케이션
- 시스템 관리자 및 개발자

### 1.3 준수 요구사항
- GDPR (일반 데이터 보호 규정)
- PCI-DSS (결제 카드 산업 데이터 보안 표준) - 해당되는 경우
- ISO/IEC 27001 정보 보안 관리
- 회사 내부 보안 정책

---

## 2. 보안 요구사항

### 2.1 인증 및 권한 부여

#### 필수 요구사항
✅ **API 키 기반 인증 구현** (CRITICAL)
- 모든 API 엔드포인트에 인증 필수
- API 키는 최소 256비트 무작위 생성
- 키 해싱: SHA-256 이상
- 키 로테이션: 90일마다

**구현 예시**:
```python
from security.patches.auth_middleware import setup_auth, verify_api_key

# API 초기화
api = FastAPI()
setup_auth(api)

# 모든 엔드포인트에 인증 적용
@api.post("/query")
async def process_query(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key)
):
    # ...
```

#### API 키 관리 절차
1. **키 생성**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **키 저장**
   - 환경변수에만 저장 (`.env` 파일)
   - 소스 코드에 절대 포함 금지
   - 버전 관리 시스템에 커밋 금지

3. **키 배포**
   - Vault 또는 AWS Secrets Manager 사용
   - 안전한 채널을 통해서만 공유
   - 평문 이메일/메신저 금지

4. **키 폐기**
   - 유출 의심 시 즉시 폐기
   - 퇴직자의 키 즉시 삭제
   - 로그에 폐기 기록 유지

#### 역할 기반 접근 제어 (RBAC)
| 역할 | 권한 | API 엔드포인트 |
|------|------|----------------|
| **Admin** | 전체 관리 | 모든 엔드포인트 |
| **Developer** | 개발 및 테스트 | `/query`, `/stop`, `/health` |
| **Viewer** | 읽기 전용 | `/health`, `/is_active` |
| **Service** | 자동화 | `/query` (제한적) |

### 2.2 네트워크 보안

#### CORS 정책 (CRITICAL)
✅ **화이트리스트 기반 CORS 설정 필수**

```python
# .env 설정
ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"
```

**금지 사항**:
```python
# ❌ 절대 금지
allow_origins=["*"]
```

**허용 기준**:
- HTTPS 프로토콜만 허용 (개발 환경 제외)
- 정확한 도메인 매칭 (서브도메인 와일드카드 금지)
- 정기적 화이트리스트 검토 (월 1회)

#### 방화벽 규칙
```bash
# 1. 기본 정책: 모든 트래픽 차단
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 2. 필요한 포트만 허용
sudo ufw allow from 10.0.0.0/8 to any port 7777 proto tcp

# 3. SSH (필요 시)
sudo ufw allow from 10.0.0.0/8 to any port 22 proto tcp

# 4. 활성화
sudo ufw enable
```

#### TLS/SSL 요구사항
- **프로덕션**: TLS 1.3 필수
- **인증서**: Let's Encrypt 또는 회사 CA
- **갱신**: 자동 갱신 설정
- **강제 HTTPS**: HTTP → HTTPS 리다이렉트

### 2.3 코드 실행 보안

#### Python 코드 실행 (CRITICAL)
✅ **샌드박스 환경 필수**

**Option 1: RestrictedPython (권장)**
```python
from security.patches.code_sandbox import SecurePythonExecutor

executor = SecurePythonExecutor(
    timeout=30,           # 30초 제한
    max_memory_mb=512     # 512MB 메모리 제한
)

result = executor.execute(user_code)
```

**Option 2: Docker 컨테이너 격리**
```bash
docker run --rm \
  --network=none \
  --memory=512m \
  --cpus=0.5 \
  --read-only \
  --security-opt=no-new-privileges \
  python:3.11-alpine python -c "$CODE"
```

**Option 3: 코드 실행 완전 비활성화**
```ini
# config.ini
[SECURITY]
allow_code_execution = false
```

#### Bash 명령 실행 (CRITICAL)
✅ **shell=False 필수, 명령 화이트리스트 적용**

```python
from security.patches.code_sandbox import SecureBashExecutor

executor = SecureBashExecutor(
    work_dir="/var/agenticseek/workspace",
    timeout=300
)

# shell=False로 안전하게 실행
result = executor.execute("ls -la")
```

**허용 명령어 화이트리스트**:
```python
ALLOWED_COMMANDS = {
    'ls', 'pwd', 'cat', 'grep', 'find',
    'head', 'tail', 'wc', 'sort', 'uniq',
    'mkdir', 'touch', 'cp', 'mv'
}
```

### 2.4 입력 검증

#### 모든 사용자 입력 검증 필수 (HIGH)
```python
from security.patches.input_validation import validate_query

@api.post("/query")
async def process_query(request: QueryRequest):
    try:
        validated_query = validate_query(request.query)
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )

    # ...
```

#### 검증 기준
| 항목 | 제한 |
|------|------|
| 최대 길이 | 10,000자 |
| 특수문자 총량 | 100개 이하 |
| 연속 특수문자 | 5개 이하 |
| Prompt Injection | 차단 |
| XSS 패턴 | 차단 |
| Command Injection | 차단 |

### 2.5 데이터 보호

#### 민감 정보 보호 (CRITICAL)
✅ **API 키 및 시크릿 암호화 필수**

**환경변수 암호화**:
```python
from cryptography.fernet import Fernet

# 1. 마스터 키 생성 (한 번만)
master_key = Fernet.generate_key()

# 2. API 키 암호화
cipher = Fernet(master_key)
encrypted_key = cipher.encrypt(b"my-api-key")

# 3. 환경변수에 저장
MASTER_KEY=<base64-encoded-master-key>
OPENAI_API_KEY_ENCRYPTED=<base64-encoded-encrypted-key>
```

**Vault 사용 (권장)**:
```python
import hvac

client = hvac.Client(url='https://vault.company.com')
client.token = os.getenv('VAULT_TOKEN')

# 시크릿 읽기
secret = client.secrets.kv.v2.read_secret_version(
    path='agenticseek/openai'
)
api_key = secret['data']['data']['api_key']
```

#### 대화 내역 암호화
```python
from cryptography.fernet import Fernet

# 대화 내역 저장 시 암호화
conversation_data = json.dumps(conversation)
encrypted = cipher.encrypt(conversation_data.encode())

with open('conversations/encrypted.bin', 'wb') as f:
    f.write(encrypted)
```

#### 로그 보안
- **민감 정보 마스킹**:
  ```python
  def mask_api_key(text):
      return re.sub(
          r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_-]+)(["\']?)',
          r'\1***MASKED***\3',
          text,
          flags=re.IGNORECASE
      )
  ```

- **로그 암호화**: 민감 로그는 암호화 저장
- **로그 로테이션**: 일 단위, 7일 보관
- **접근 제한**: 로그 디렉토리 권한 700

---

## 3. 배포 및 운영

### 3.1 배포 환경

#### 프로덕션 환경 요구사항
```yaml
# Docker Compose 보안 설정
services:
  agenticseek:
    image: agenticseek:latest
    security_opt:
      - no-new-privileges:true
      - seccomp=unconfined
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=100m
    networks:
      - internal
    environment:
      - AGENTICSEEK_API_KEYS=${API_KEYS}
      - ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7777/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  internal:
    driver: bridge
    internal: true  # 외부 인터넷 차단
```

#### 환경 분리
| 환경 | 용도 | 보안 수준 | 데이터 |
|------|------|-----------|--------|
| **Development** | 개발 | 낮음 | 테스트 데이터 |
| **Staging** | 통합 테스트 | 중간 | 익명화된 데이터 |
| **Production** | 운영 | 최고 | 실제 데이터 |

### 3.2 모니터링

#### 보안 이벤트 모니터링
```python
# 감사 로깅
import logging
import json

audit_logger = logging.getLogger('audit')

def log_security_event(event_type, user, details):
    audit_logger.info(json.dumps({
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'user': user,
        'ip': request.client.host,
        'details': details
    }))

# 사용 예시
log_security_event(
    event_type='authentication_failure',
    user='unknown',
    details={'reason': 'invalid_api_key'}
)
```

#### 알림 설정
| 이벤트 | 심각도 | 알림 채널 | 조치 |
|--------|--------|-----------|------|
| 인증 실패 (5회 이상) | HIGH | Slack, Email | 계정 잠금 |
| 코드 실행 실패 | MEDIUM | Slack | 검토 |
| API 키 유출 의심 | CRITICAL | 전화, SMS | 즉시 폐기 |
| 비정상 트래픽 | HIGH | Slack | Rate limit |

### 3.3 백업 및 복구

#### 백업 정책
- **빈도**: 일 1회 (자동)
- **보관 기간**: 30일
- **암호화**: AES-256
- **저장 위치**: 오프사이트 스토리지

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backup/agenticseek"
ENCRYPT_KEY=$(cat /secure/backup.key)

# 1. 대화 내역 백업
tar -czf "$BACKUP_DIR/conversations-$DATE.tar.gz" conversations/

# 2. 설정 백업
cp config.ini "$BACKUP_DIR/config-$DATE.ini"
cp .env "$BACKUP_DIR/env-$DATE.txt"

# 3. 암호화
openssl enc -aes-256-cbc -salt \
  -in "$BACKUP_DIR/conversations-$DATE.tar.gz" \
  -out "$BACKUP_DIR/conversations-$DATE.tar.gz.enc" \
  -pass pass:$ENCRYPT_KEY

# 4. 오프사이트 전송
aws s3 cp "$BACKUP_DIR/conversations-$DATE.tar.gz.enc" \
  s3://company-backup/agenticseek/

# 5. 로컬 정리 (30일 이상 삭제)
find "$BACKUP_DIR" -name "*.enc" -mtime +30 -delete
```

---

## 4. 사고 대응

### 4.1 보안 사고 분류

| 심각도 | 설명 | 예시 |
|--------|------|------|
| **P0 (긴급)** | 즉각 대응 필요 | API 키 유출, 시스템 장악 |
| **P1 (높음)** | 24시간 내 대응 | 인증 우회, 데이터 유출 |
| **P2 (중간)** | 72시간 내 대응 | 취약점 발견 |
| **P3 (낮음)** | 1주일 내 대응 | 잠재적 위험 |

### 4.2 사고 대응 절차

#### API 키 유출 시
```bash
# 1. 즉시 조치 (5분 이내)
# 유출된 키 식별 및 폐기
sed -i '/compromised-key/d' .env
systemctl restart agenticseek

# 2. 새 키 생성 및 배포
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "AGENTICSEEK_API_KEYS=\"$NEW_KEY\"" >> .env

# 3. 로그 분석
grep "compromised-key" .logs/*.log > incident-report.txt

# 4. 사용자 통지
# 모든 사용자에게 새 API 키 배포
```

#### 시스템 침해 시
```bash
# 1. 시스템 격리
sudo ufw deny in on eth0
docker stop agenticseek

# 2. 포렌식 증거 수집
docker exec agenticseek tar -czf /tmp/forensics.tar.gz /var/log/ /tmp/
docker cp agenticseek:/tmp/forensics.tar.gz ./evidence/

# 3. 백업에서 복구
./restore-from-backup.sh 20251101

# 4. 보안 강화 후 재시작
# 취약점 패치 적용
# 새 API 키 생성
# 방화벽 규칙 강화
```

### 4.3 사후 조치
1. **근본 원인 분석 (Root Cause Analysis)**
2. **재발 방지 대책 수립**
3. **보안 정책 업데이트**
4. **직원 교육**
5. **사고 보고서 작성**

---

## 5. 규정 준수

### 5.1 GDPR 준수

#### 개인 데이터 처리
- **수집 최소화**: 필요한 데이터만 수집
- **목적 제한**: 명시된 목적으로만 사용
- **저장 제한**: 30일 이후 자동 삭제
- **암호화**: 전송 및 저장 시 암호화

#### 사용자 권리
- **열람권**: 자신의 데이터 확인 가능
- **정정권**: 부정확한 데이터 수정
- **삭제권**: 데이터 삭제 요청
- **이동권**: 데이터 내보내기

```python
# GDPR 준수 API
@api.delete("/user/{user_id}/data")
async def delete_user_data(
    user_id: str,
    api_key: str = Depends(verify_api_key)
):
    """사용자 데이터 삭제 (삭제권)"""
    # 대화 내역 삭제
    shutil.rmtree(f"conversations/{user_id}")

    # 로그에서 개인정보 제거
    anonymize_logs(user_id)

    return {"status": "deleted", "user_id": user_id}
```

### 5.2 감사 및 인증

#### 연간 보안 감사
- **외부 감사**: 독립된 보안 회사
- **침투 테스트**: 분기별
- **코드 리뷰**: 릴리스마다
- **취약점 스캔**: 주간

#### 인증
- **ISO 27001**: 정보 보안 관리 시스템
- **SOC 2**: 서비스 조직 통제
- **PCI-DSS**: 결제 카드 데이터 보안 (해당 시)

---

## 6. 교육 및 인식

### 6.1 직원 교육

#### 필수 교육 프로그램
| 대상 | 주제 | 빈도 |
|------|------|------|
| **전체 직원** | 보안 기본 인식 | 연 1회 |
| **개발자** | 시큐어 코딩 | 분기별 |
| **관리자** | 시스템 보안 관리 | 반기별 |
| **보안팀** | 최신 위협 대응 | 월별 |

#### 교육 내용
1. **API 키 보안**
   - 키 생성 및 저장
   - 유출 예방
   - 사고 대응

2. **코드 실행 위험**
   - 임의 코드 실행 위험성
   - 샌드박스 사용법
   - 안전한 코딩

3. **사회 공학 대응**
   - 피싱 메일 식별
   - 의심스러운 요청 거부
   - 보고 절차

### 6.2 보안 인식 캠페인

#### 월간 보안 팁
```
11월: "API 키는 절대 GitHub에 커밋하지 마세요!"
12월: "강력한 비밀번호 + MFA 사용하기"
1월: "의심스러운 이메일은 보안팀에 보고"
```

---

## 7. 부록

### 7.1 보안 체크리스트

프로덕션 배포 전 필수 점검:

#### 인증/인가
- [ ] API 키 인증 구현
- [ ] RBAC 설정
- [ ] 세션 타임아웃 설정

#### 네트워크
- [ ] CORS 화이트리스트 설정
- [ ] HTTPS 강제
- [ ] 방화벽 규칙 적용

#### 코드 실행
- [ ] 샌드박스 적용
- [ ] shell=True 제거
- [ ] 입력 검증

#### 데이터
- [ ] API 키 암호화
- [ ] 로그 민감정보 마스킹
- [ ] 백업 암호화

#### 모니터링
- [ ] 감사 로깅 활성화
- [ ] 알림 설정
- [ ] 헬스체크 구현

### 7.2 긴급 연락처

| 역할 | 이름 | 연락처 | 비고 |
|------|------|--------|------|
| **보안 책임자** | [이름] | [전화번호] | 24/7 대기 |
| **시스템 관리자** | [이름] | [전화번호] | 평일 09-18시 |
| **개발팀 리더** | [이름] | [전화번호] | 평일 09-18시 |
| **외부 보안팀** | [회사명] | [전화번호] | 계약 기반 |

### 7.3 관련 문서

- [보안 코드 리뷰 보고서](./SECURITY_REVIEW_KR.md)
- [POC 취약점 시연](./poc_vulnerabilities.py)
- [보안 패치 가이드](./patches/)
- [침투 테스트 보고서](./pentest/)

---

## 변경 이력

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|-----------|
| 1.0 | 2025-11-01 | Security Team | 최초 작성 |

---

**승인**:
- 보안 책임자: _________________ 날짜: _______
- CTO: _________________ 날짜: _______
- 준법감시인: _________________ 날짜: _______
