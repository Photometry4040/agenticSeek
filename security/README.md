# AgenticSeek 보안 개선 패키지

이 디렉토리는 AgenticSeek의 보안을 강화하기 위한 도구, 패치, 정책 및 테스트를 포함합니다.

## 📁 디렉토리 구조

```
security/
├── README.md                          # 이 파일
├── ENTERPRISE_SECURITY_POLICY.md      # 기업 보안 정책
├── poc_vulnerabilities.py             # POC (취약점 시연)
├── patches/                           # 보안 패치
│   ├── auth_middleware.py            # API 키 인증
│   ├── secure_cors.py                # 안전한 CORS 설정
│   ├── code_sandbox.py               # 코드 실행 샌드박스
│   └── input_validation.py           # 입력 검증
└── pentest/                           # 침투 테스트
    └── automated_pentest.sh          # 자동화된 보안 테스트
```

---

## 🚀 빠른 시작

### 1. POC - 취약점 확인

현재 시스템의 취약점을 확인하려면:

```bash
# AgenticSeek 서버가 실행 중이어야 합니다
python api.py &

# POC 실행
cd security
python poc_vulnerabilities.py http://localhost:7777
```

**출력 예시**:
```
POC 1: No Authentication Vulnerability
  [!] GET /query
      Status: 200
      Auth Required: NO ❌
      VULNERABLE - Accessed without authentication

POC 2: Arbitrary Code Execution
  [!] Attack: System Information Disclosure
      Danger: Reveals system information
      Severity: CRITICAL ⚠️
```

### 2. 보안 패치 적용

#### Step 1: 인증 추가

```python
# api.py에 추가
from security.patches.auth_middleware import setup_auth, verify_api_key

# 미들웨어 설정
setup_auth(api)

# 엔드포인트 보호
@api.post("/query")
async def process_query(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key)  # ✅ 인증 필수
):
    # ...
```

**환경변수 설정**:
```bash
# .env 파일
AGENTICSEEK_API_KEYS="your-secure-api-key-here"
```

**API 키 생성**:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### Step 2: CORS 보안

```python
# api.py의 CORS 설정 교체
from security.patches.secure_cors import setup_secure_cors

# 기존 코드 제거:
# api.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 새로운 코드:
setup_secure_cors(api)
```

**환경변수 설정**:
```bash
# .env 파일
ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"
```

#### Step 3: 코드 실행 샌드박스

```python
# sources/tools/PyInterpreter.py 교체
from security.patches.code_sandbox import SecurePythonExecutor

class PyInterpreter(Tools):
    def __init__(self):
        super().__init__()
        self.executor = SecurePythonExecutor(
            timeout=30,
            max_memory_mb=512
        )

    def execute(self, codes: str, safety=False) -> str:
        return self.executor.execute(codes)
```

#### Step 4: 입력 검증

```python
# api.py에 추가
from security.patches.input_validation import validate_query, ValidationError

@api.post("/query")
async def process_query(request: QueryRequest):
    try:
        validated_query = validate_query(request.query)
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )

    # validated_query 사용
    # ...
```

### 3. 침투 테스트 실행

보안 패치 적용 후 시스템을 테스트:

```bash
cd security/pentest
./automated_pentest.sh http://localhost:7777
```

**출력 예시**:
```
═══════════════════════════════════════════════════════════════
2. AUTHENTICATION BYPASS TESTS
═══════════════════════════════════════════════════════════════

[*] Testing: No Authentication
    Severity: CRITICAL
[✓] SAFE: API requires authentication (HTTP 403)

SUMMARY
═══════════════════════════════════════════════════════════════
Total Tests: 10
Vulnerabilities Found: 0

[✓] No critical vulnerabilities detected
```

---

## 📚 문서

### 보안 정책
- **[기업 보안 정책](./ENTERPRISE_SECURITY_POLICY.md)**: 회사 환경에서 사용하기 위한 상세 정책
  - 인증/인가 요구사항
  - 네트워크 보안
  - 데이터 보호
  - 사고 대응
  - 규정 준수 (GDPR, ISO 27001)

### 코드 리뷰
- **[보안 코드 리뷰](../SECURITY_REVIEW_KR.md)**: 전체 코드베이스 보안 분석
  - CRITICAL 취약점 4개
  - HIGH 취약점 3개
  - MEDIUM 취약점 3개
  - 상세 권장사항

---

## 🛡️ 보안 패치 상세

### 1. 인증 미들웨어 (auth_middleware.py)

**기능**:
- API 키 기반 인증
- SHA-256 해시 저장
- 레이트 리미팅 (분당 60회)
- 감사 로깅

**사용 예시**:
```python
from security.patches.auth_middleware import verify_api_key, generate_api_key

# API 키 생성
new_key = generate_api_key()
print(f"API Key: {new_key}")

# 엔드포인트 보호
@api.get("/protected")
async def protected_route(api_key: str = Depends(verify_api_key)):
    return {"message": "Authenticated!"}
```

### 2. 안전한 CORS (secure_cors.py)

**기능**:
- 화이트리스트 기반 origin 검증
- HTTPS 강제 (프로덕션)
- 제한된 HTTP 메서드
- Preflight 캐싱 (1시간)

**설정 예시**:
```bash
# 개발 환경
ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8000"

# 프로덕션 환경
ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"
```

### 3. 코드 샌드박스 (code_sandbox.py)

**기능**:
- RestrictedPython 지원
- Docker 컨테이너 격리
- 리소스 제한 (메모리, CPU, 시간)
- 네트워크 격리

**Python 실행**:
```python
from security.patches.code_sandbox import SecurePythonExecutor

executor = SecurePythonExecutor(timeout=30, max_memory_mb=512)

# 안전한 코드
result = executor.execute("print('Hello')")  # ✅ 실행

# 위험한 코드
result = executor.execute("import os; os.system('rm -rf /')")  # ❌ 차단
# SecurityError: Code contains prohibited operations
```

**Bash 실행**:
```python
from security.patches.code_sandbox import SecureBashExecutor

executor = SecureBashExecutor(work_dir="/var/workspace", timeout=300)

# 안전한 명령
result = executor.execute("ls -la")  # ✅ 허용

# 위험한 명령
result = executor.execute("rm -rf /")  # ❌ 차단
# SecurityError: Command not allowed: rm
```

### 4. 입력 검증 (input_validation.py)

**기능**:
- Prompt Injection 차단
- XSS 패턴 검증
- Command Injection 방지
- SQL Injection 방지
- Path Traversal 차단

**사용 예시**:
```python
from security.patches.input_validation import validate_query, ValidationError

try:
    safe_query = validate_query(user_input)
    # safe_query 사용
except ValidationError as e:
    return {"error": str(e)}
```

**차단되는 패턴**:
```python
# Prompt Injection
"Ignore all previous instructions..."  # ❌ 차단

# XSS
"<script>alert('xss')</script>"  # ❌ 차단

# Command Injection
"ls; rm -rf /"  # ❌ 차단

# SQL Injection
"'; DROP TABLE users; --"  # ❌ 차단

# Path Traversal
"../../../etc/passwd"  # ❌ 차단
```

---

## 🧪 테스트

### POC 테스트
```bash
# 모든 취약점 시연
python security/poc_vulnerabilities.py

# 특정 타겟 지정
python security/poc_vulnerabilities.py http://target:7777
```

### 침투 테스트
```bash
# 자동화된 보안 테스트
cd security/pentest
./automated_pentest.sh http://localhost:7777

# 보고서 생성
# pentest_report_YYYYMMDD_HHMMSS.txt
```

### 단위 테스트
```bash
# 입력 검증 테스트
python security/patches/input_validation.py

# 코드 샌드박스 테스트
python security/patches/code_sandbox.py

# CORS 설정 테스트
python security/patches/secure_cors.py
```

---

## 📋 체크리스트

프로덕션 배포 전 필수 점검:

### 인증/인가
- [ ] API 키 인증 구현 완료
- [ ] `.env`에 안전한 API 키 설정
- [ ] API 키를 Vault에 저장
- [ ] 모든 엔드포인트에 인증 적용

### 네트워크
- [ ] CORS 화이트리스트 설정
- [ ] HTTPS 강제 적용
- [ ] 방화벽 규칙 구성
- [ ] VPN 또는 내부 네트워크만 허용

### 코드 실행
- [ ] Python 샌드박스 적용
- [ ] Bash `shell=False` 적용
- [ ] 리소스 제한 설정
- [ ] 타임아웃 설정

### 입력 검증
- [ ] 모든 엔드포인트에 검증 적용
- [ ] 최대 길이 제한
- [ ] 위험 패턴 차단
- [ ] 새니타이제이션 적용

### 모니터링
- [ ] 감사 로깅 활성화
- [ ] 알림 설정 (Slack, Email)
- [ ] 헬스체크 구현
- [ ] 메트릭 수집

### 데이터
- [ ] API 키 암호화
- [ ] 로그 민감정보 마스킹
- [ ] 백업 암호화
- [ ] GDPR 준수

---

## 🔧 문제 해결

### 1. "RestrictedPython not installed" 오류

```bash
pip install RestrictedPython
```

또는 Docker 샌드박스 사용:
```bash
docker pull python:3.11-alpine
```

### 2. "No API keys configured" 경고

```bash
# .env 파일에 API 키 추가
echo 'AGENTICSEEK_API_KEYS="your-key-here"' >> .env
```

### 3. CORS 오류

```bash
# 허용된 origin 확인
grep ALLOWED_ORIGINS .env

# 추가
echo 'ALLOWED_ORIGINS="https://your-domain.com"' >> .env
```

### 4. 코드 실행 실패

```bash
# 로그 확인
tail -f .logs/sandbox.log

# 타임아웃 증가
# code_sandbox.py에서 timeout=60으로 설정
```

---

## 📞 지원

### 문서
- [보안 코드 리뷰](../SECURITY_REVIEW_KR.md)
- [기업 보안 정책](./ENTERPRISE_SECURITY_POLICY.md)
- [메인 README](../README.md)

### 문의
- 보안 이슈: security@company.com
- GitHub Issues: https://github.com/Photometry4040/agenticSeek/issues

---

## 📄 라이선스

이 보안 패키지는 AgenticSeek 프로젝트와 동일한 라이선스를 따릅니다.

---

**⚠️ 중요**: 이 보안 패치는 즉시 적용을 권장하지만, 프로덕션 환경에 배포하기 전에 개발 환경에서 충분히 테스트하세요.

**🔒 보안**: 취약점을 발견하면 공개 이슈가 아닌 security@company.com으로 직접 보고해주세요.
