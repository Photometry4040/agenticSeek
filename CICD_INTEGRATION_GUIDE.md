# AgenticSeek CI/CD 파이프라인 통합 가이드

## 📋 목차

1. [CI/CD 개요](#1-cicd-개요)
2. [GitHub Actions 설정](#2-github-actions-설정)
3. [GitLab CI 설정](#3-gitlab-ci-설정)
4. [Jenkins 파이프라인](#4-jenkins-파이프라인)
5. [보안 스캔 통합](#5-보안-스캔-통합)
6. [자동 배포](#6-자동-배포)
7. [롤백 전략](#7-롤백-전략)
8. [모니터링 및 알림](#8-모니터링-및-알림)

---

## 1. CI/CD 개요

### 1.1 파이프라인 아키텍처

```
┌─────────────┐
│  Git Push   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         CI Pipeline                 │
│  1. Lint & Format Check             │
│  2. Unit Tests                      │
│  3. Integration Tests               │
│  4. Security Scan                   │
│  5. Build Docker Image              │
│  6. Push to Registry                │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         CD Pipeline                 │
│  1. Deploy to Staging               │
│  2. Smoke Tests                     │
│  3. Security Validation             │
│  4. Deploy to Production            │
│  5. Health Check                    │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────┐
│ Monitoring  │
└─────────────┘
```

### 1.2 브랜치 전략

```
main (production)
  │
  ├─── release/v1.0.0 (staging)
  │      │
  │      └─── feature/auth-improvement
  │      └─── feature/new-llm-provider
  │
  └─── hotfix/security-patch
```

**브랜치 규칙:**
- `main`: 프로덕션 환경, 태그된 릴리즈만
- `release/*`: 스테이징 환경, RC 빌드
- `feature/*`: 개발 환경, 기능 개발
- `hotfix/*`: 긴급 패치, main에 직접 머지

---

## 2. GitHub Actions 설정

### 2.1 CI 워크플로우

```yaml
# .github/workflows/ci.yml

name: CI Pipeline

on:
  push:
    branches: [ main, release/*, feature/* ]
  pull_request:
    branches: [ main, release/* ]

env:
  PYTHON_VERSION: '3.10'
  DOCKER_REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # === 1. 코드 품질 검사 ===
  lint-and-format:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip packages
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install black flake8 pylint mypy

      - name: Run Black (formatter)
        run: black --check .

      - name: Run Flake8 (linter)
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

      - name: Run Pylint
        run: pylint **/*.py --fail-under=8.0

      - name: Run MyPy (type checking)
        run: mypy . --ignore-missing-imports

  # === 2. 단위 테스트 ===
  unit-tests:
    runs-on: ubuntu-latest
    needs: lint-and-format
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run tests with coverage
        run: |
          pytest tests/ \
            --cov=. \
            --cov-report=xml \
            --cov-report=html \
            --junitxml=test-results.xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

      - name: Upload test results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results
          path: test-results.xml

  # === 3. 보안 스캔 ===
  security-scan:
    runs-on: ubuntu-latest
    needs: lint-and-format
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Run Security Quick Scan
        run: |
          pip install -r requirements.txt
          python security/quick_scan.py

      - name: Run Bandit (security linter)
        run: |
          pip install bandit
          bandit -r . -f json -o bandit-report.json

      - name: Run Safety (dependency check)
        run: |
          pip install safety
          safety check --json > safety-report.json

      - name: Run Trivy (vulnerability scanner)
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

      - name: Upload security reports
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            bandit-report.json
            safety-report.json

  # === 4. 통합 테스트 ===
  integration-tests:
    runs-on: ubuntu-latest
    needs: [unit-tests, security-scan]
    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run integration tests
        env:
          REDIS_BASE_URL: redis://localhost:6379/0
        run: |
          pytest tests/integration/ -v

  # === 5. Docker 이미지 빌드 ===
  build-docker:
    runs-on: ubuntu-latest
    needs: [unit-tests, security-scan]
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.DOCKER_REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=sha,prefix={{branch}}-

      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Run Trivy scan on Docker image
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-image-results.sarif'

  # === 6. 침투 테스트 ===
  penetration-test:
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v3

      - name: Start API server
        run: |
          pip install -r requirements.txt
          python api_secure.py &
          sleep 10

      - name: Generate test API key
        run: |
          python security/tools/generate_api_keys.py --count 1 --export

      - name: Run penetration tests
        run: |
          cd security/pentest
          bash automated_pentest.sh http://localhost:7777

      - name: Upload pentest report
        uses: actions/upload-artifact@v3
        with:
          name: pentest-report
          path: security/pentest/pentest_report_*.txt

  # === 7. 성능 테스트 ===
  performance-test:
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install locust

      - name: Start API server
        run: |
          python api_secure.py &
          sleep 10

      - name: Run Locust load test
        run: |
          locust -f loadtest/locustfile.py \
            --host=http://localhost:7777 \
            --users 50 \
            --spawn-rate 5 \
            --run-time 2m \
            --headless \
            --html=loadtest-report.html

      - name: Upload performance report
        uses: actions/upload-artifact@v3
        with:
          name: performance-report
          path: loadtest-report.html
```

### 2.2 CD 워크플로우

```yaml
# .github/workflows/cd.yml

name: CD Pipeline

on:
  push:
    branches: [ main ]
    tags: [ 'v*.*.*' ]

env:
  DOCKER_REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # === 1. 스테이징 배포 ===
  deploy-staging:
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: https://staging.company.com
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Deploy to ECS (Staging)
        run: |
          aws ecs update-service \
            --cluster agenticseek-staging \
            --service agenticseek-api \
            --force-new-deployment

      - name: Wait for deployment
        run: |
          aws ecs wait services-stable \
            --cluster agenticseek-staging \
            --services agenticseek-api

      - name: Health check
        run: |
          for i in {1..30}; do
            if curl -f https://staging.company.com/health; then
              echo "✅ Staging deployment successful"
              exit 0
            fi
            echo "Waiting... ($i/30)"
            sleep 10
          done
          echo "❌ Health check failed"
          exit 1

  # === 2. 스모크 테스트 ===
  smoke-test:
    runs-on: ubuntu-latest
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v3

      - name: Run smoke tests
        run: |
          pip install pytest requests
          pytest tests/smoke/ --base-url=https://staging.company.com

  # === 3. 프로덕션 배포 (승인 필요) ===
  deploy-production:
    runs-on: ubuntu-latest
    needs: smoke-test
    environment:
      name: production
      url: https://app.company.com
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Create backup
        run: |
          timestamp=$(date +%Y%m%d_%H%M%S)
          aws s3 sync s3://agenticseek-prod/conversations/ \
            s3://agenticseek-backup/$timestamp/conversations/

      - name: Blue-Green Deployment
        run: |
          # 새 태스크 정의 생성
          NEW_TASK_DEF=$(aws ecs describe-task-definition \
            --task-definition agenticseek-prod \
            --query 'taskDefinition' | \
            jq '.containerDefinitions[0].image = "${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.ref_name }}"')

          aws ecs register-task-definition --cli-input-json "$NEW_TASK_DEF"

          # 새 서비스로 트래픽 전환
          aws ecs update-service \
            --cluster agenticseek-prod \
            --service agenticseek-api \
            --task-definition agenticseek-prod \
            --force-new-deployment

      - name: Wait for production deployment
        run: |
          aws ecs wait services-stable \
            --cluster agenticseek-prod \
            --services agenticseek-api

      - name: Production health check
        run: |
          for i in {1..30}; do
            if curl -f https://app.company.com/health; then
              echo "✅ Production deployment successful"
              exit 0
            fi
            echo "Waiting... ($i/30)"
            sleep 10
          done
          echo "❌ Production health check failed - initiating rollback"
          exit 1

      - name: Rollback on failure
        if: failure()
        run: |
          echo "🔄 Rolling back to previous version"
          aws ecs update-service \
            --cluster agenticseek-prod \
            --service agenticseek-api \
            --task-definition agenticseek-prod:${{ github.event.before }} \
            --force-new-deployment

      - name: Notify Slack
        if: always()
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "Production Deployment: ${{ job.status }}",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*AgenticSeek Production Deployment*\nVersion: ${{ github.ref_name }}\nStatus: ${{ job.status }}\nCommit: ${{ github.sha }}"
                  }
                }
              ]
            }
```

### 2.3 보안 스캔 워크플로우

```yaml
# .github/workflows/security.yml

name: Security Scan

on:
  schedule:
    - cron: '0 0 * * *'  # 매일 자정
  workflow_dispatch:

jobs:
  security-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run comprehensive security scan
        run: |
          python security/quick_scan.py > security-report.txt

      - name: Run dependency audit
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --format json > audit-report.json

      - name: SAST with Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/python
            p/ci

      - name: Create GitHub Issue on failure
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '🚨 Security Scan Failed',
              body: 'Automated security scan detected vulnerabilities. Please review the workflow logs.',
              labels: ['security', 'high-priority']
            })
```

---

## 3. GitLab CI 설정

### 3.1 .gitlab-ci.yml

```yaml
# .gitlab-ci.yml

stages:
  - lint
  - test
  - security
  - build
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  IMAGE_TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_REF_SLUG

# === 캐싱 설정 ===
cache:
  paths:
    - .cache/pip
    - venv/

before_script:
  - python -m venv venv
  - source venv/bin/activate
  - pip install -r requirements.txt

# === 1. 린트 ===
lint:
  stage: lint
  image: python:3.10
  script:
    - pip install black flake8 pylint
    - black --check .
    - flake8 .
    - pylint **/*.py --fail-under=8.0
  only:
    - merge_requests
    - main

# === 2. 단위 테스트 ===
unit-test:
  stage: test
  image: python:3.10
  services:
    - redis:7-alpine
  variables:
    REDIS_BASE_URL: "redis://redis:6379/0"
  script:
    - pip install pytest pytest-cov
    - pytest tests/ --cov=. --cov-report=xml --cov-report=term
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml

# === 3. 보안 스캔 ===
security-scan:
  stage: security
  image: python:3.10
  script:
    - python security/quick_scan.py
    - pip install bandit safety
    - bandit -r . -f json -o bandit-report.json
    - safety check --json > safety-report.json
  artifacts:
    paths:
      - bandit-report.json
      - safety-report.json
    expire_in: 1 week

# === 4. Docker 이미지 빌드 ===
build:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $IMAGE_TAG .
    - docker push $IMAGE_TAG
  only:
    - main
    - tags

# === 5. 스테이징 배포 ===
deploy-staging:
  stage: deploy
  image: alpine:latest
  before_script:
    - apk add --no-cache curl
  script:
    - |
      curl -X POST https://staging.company.com/deploy \
        -H "Authorization: Bearer $DEPLOY_TOKEN" \
        -d "image=$IMAGE_TAG"
  environment:
    name: staging
    url: https://staging.company.com
  only:
    - main

# === 6. 프로덕션 배포 ===
deploy-production:
  stage: deploy
  image: alpine:latest
  before_script:
    - apk add --no-cache curl
  script:
    - |
      curl -X POST https://app.company.com/deploy \
        -H "Authorization: Bearer $DEPLOY_TOKEN" \
        -d "image=$IMAGE_TAG"
  environment:
    name: production
    url: https://app.company.com
  when: manual  # 수동 승인 필요
  only:
    - tags
```

---

## 4. Jenkins 파이프라인

### 4.1 Jenkinsfile

```groovy
// Jenkinsfile

pipeline {
    agent any

    environment {
        DOCKER_REGISTRY = 'registry.company.com'
        IMAGE_NAME = 'agenticseek'
        PYTHON_VERSION = '3.10'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Lint') {
            parallel {
                stage('Black') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip install black
                            black --check .
                        '''
                    }
                }
                stage('Flake8') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip install flake8
                            flake8 .
                        '''
                    }
                }
                stage('Pylint') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip install pylint
                            pylint **/*.py --fail-under=8.0
                        '''
                    }
                }
            }
        }

        stage('Test') {
            steps {
                sh '''
                    . venv/bin/activate
                    pip install pytest pytest-cov
                    pytest tests/ --cov=. --cov-report=xml --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                    publishCoverage adapters: [coberturaAdapter('coverage.xml')]
                }
            }
        }

        stage('Security Scan') {
            parallel {
                stage('Quick Scan') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            python security/quick_scan.py
                        '''
                    }
                }
                stage('Bandit') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip install bandit
                            bandit -r . -f json -o bandit-report.json
                        '''
                    }
                }
                stage('Safety') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip install safety
                            safety check --json > safety-report.json
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: '*-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    def imageTag = "${DOCKER_REGISTRY}/${IMAGE_NAME}:${env.GIT_COMMIT}"
                    docker.build(imageTag)
                }
            }
        }

        stage('Push Docker Image') {
            when {
                branch 'main'
            }
            steps {
                script {
                    def imageTag = "${DOCKER_REGISTRY}/${IMAGE_NAME}:${env.GIT_COMMIT}"
                    docker.withRegistry("https://${DOCKER_REGISTRY}", 'docker-registry-credentials') {
                        docker.image(imageTag).push()
                        docker.image(imageTag).push('latest')
                    }
                }
            }
        }

        stage('Deploy to Staging') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    ssh deploy@staging.company.com << EOF
                    cd /opt/agenticseek
                    docker-compose pull
                    docker-compose up -d
                    EOF
                '''
            }
        }

        stage('Smoke Test') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    . venv/bin/activate
                    pip install pytest requests
                    pytest tests/smoke/ --base-url=https://staging.company.com
                '''
            }
        }

        stage('Deploy to Production') {
            when {
                tag pattern: "v\\d+\\.\\d+\\.\\d+", comparator: "REGEXP"
            }
            input {
                message "Deploy to production?"
                ok "Deploy"
            }
            steps {
                sh '''
                    ssh deploy@app.company.com << EOF
                    cd /opt/agenticseek
                    docker-compose pull
                    docker-compose up -d
                    EOF
                '''
            }
        }

        stage('Health Check') {
            when {
                tag pattern: "v\\d+\\.\\d+\\.\\d+", comparator: "REGEXP"
            }
            steps {
                script {
                    retry(30) {
                        sh 'curl -f https://app.company.com/health || sleep 10'
                    }
                }
            }
        }
    }

    post {
        success {
            slackSend(
                color: 'good',
                message: "✅ Build #${env.BUILD_NUMBER} succeeded for ${env.JOB_NAME}"
            )
        }
        failure {
            slackSend(
                color: 'danger',
                message: "❌ Build #${env.BUILD_NUMBER} failed for ${env.JOB_NAME}"
            )
        }
        always {
            cleanWs()
        }
    }
}
```

---

## 5. 보안 스캔 통합

### 5.1 SAST (Static Application Security Testing)

```yaml
# .github/workflows/sast.yml

name: SAST Scan

on:
  push:
    branches: [ main, release/* ]
  pull_request:
    branches: [ main ]

jobs:
  sonarcloud:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # 전체 히스토리 필요

      - name: SonarCloud Scan
        uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
        with:
          args: >
            -Dsonar.projectKey=agenticseek
            -Dsonar.organization=company
            -Dsonar.python.coverage.reportPaths=coverage.xml

  codeql:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v3

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v2
        with:
          languages: python

      - name: Autobuild
        uses: github/codeql-action/autobuild@v2

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v2
```

### 5.2 DAST (Dynamic Application Security Testing)

```yaml
# .github/workflows/dast.yml

name: DAST Scan

on:
  schedule:
    - cron: '0 2 * * 0'  # 매주 일요일 오전 2시
  workflow_dispatch:

jobs:
  zap-scan:
    runs-on: ubuntu-latest
    steps:
      - name: ZAP Scan
        uses: zaproxy/action-full-scan@v0.4.0
        with:
          target: 'https://staging.company.com'
          rules_file_name: '.zap/rules.tsv'
          cmd_options: '-a'

      - name: Upload ZAP Report
        uses: actions/upload-artifact@v3
        with:
          name: zap-report
          path: report_html.html
```

### 5.3 의존성 스캔

```yaml
# .github/workflows/dependency-scan.yml

name: Dependency Scan

on:
  push:
    paths:
      - 'requirements.txt'
      - 'package.json'
  schedule:
    - cron: '0 0 * * 1'  # 매주 월요일

jobs:
  snyk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Snyk to check for vulnerabilities
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high

  dependabot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Check for outdated dependencies
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt --format json -o audit.json

      - name: Create issue if vulnerabilities found
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '🔒 Dependency Vulnerabilities Detected',
              body: 'Please check the workflow logs for details.',
              labels: ['dependencies', 'security']
            })
```

---

## 6. 자동 배포

### 6.1 Kubernetes 배포 (Helm)

```yaml
# .github/workflows/k8s-deploy.yml

name: Kubernetes Deployment

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure kubectl
        uses: azure/setup-kubectl@v3

      - name: Set up Helm
        uses: azure/setup-helm@v3

      - name: Deploy to Kubernetes
        run: |
          # kubeconfig 설정
          echo "${{ secrets.KUBECONFIG }}" | base64 -d > kubeconfig.yaml
          export KUBECONFIG=kubeconfig.yaml

          # Helm 배포
          helm upgrade --install agenticseek ./helm/agenticseek \
            --namespace agenticseek \
            --set image.tag=${{ github.ref_name }} \
            --set secrets.apiKeys="${{ secrets.API_KEYS }}" \
            --wait \
            --timeout 5m

      - name: Verify deployment
        run: |
          kubectl rollout status deployment/agenticseek-api -n agenticseek
          kubectl get pods -n agenticseek
```

### 6.2 Terraform 인프라 배포

```yaml
# .github/workflows/terraform.yml

name: Terraform

on:
  push:
    paths:
      - 'terraform/**'
    branches:
      - main

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2

      - name: Terraform Init
        working-directory: terraform
        run: terraform init

      - name: Terraform Plan
        working-directory: terraform
        run: terraform plan -out=tfplan

      - name: Terraform Apply
        if: github.ref == 'refs/heads/main'
        working-directory: terraform
        run: terraform apply -auto-approve tfplan
```

---

## 7. 롤백 전략

### 7.1 자동 롤백

```yaml
# .github/workflows/auto-rollback.yml

name: Auto Rollback

on:
  workflow_run:
    workflows: ["CD Pipeline"]
    types:
      - completed

jobs:
  check-and-rollback:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    steps:
      - uses: actions/checkout@v3

      - name: Get previous stable version
        id: previous
        run: |
          # 마지막 성공한 배포 태그 찾기
          PREV_TAG=$(git tag --sort=-v:refname | grep -v "${{ github.ref_name }}" | head -1)
          echo "tag=$PREV_TAG" >> $GITHUB_OUTPUT

      - name: Rollback to previous version
        run: |
          kubectl set image deployment/agenticseek-api \
            api=registry.company.com/agenticseek:${{ steps.previous.outputs.tag }} \
            -n agenticseek

      - name: Notify team
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "🔄 Auto-rollback triggered",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Automatic Rollback*\nRolled back from ${{ github.ref_name }} to ${{ steps.previous.outputs.tag }}"
                  }
                }
              ]
            }
```

### 7.2 수동 롤백 스크립트

```bash
#!/bin/bash
# scripts/rollback.sh

set -e

PREVIOUS_VERSION=$1

if [ -z "$PREVIOUS_VERSION" ]; then
    echo "Usage: ./rollback.sh <version>"
    echo "Example: ./rollback.sh v1.0.0"
    exit 1
fi

echo "🔄 Rolling back to version $PREVIOUS_VERSION"

# Kubernetes 롤백
kubectl rollout undo deployment/agenticseek-api -n agenticseek --to-revision=0

# 또는 특정 버전으로
kubectl set image deployment/agenticseek-api \
    api=registry.company.com/agenticseek:$PREVIOUS_VERSION \
    -n agenticseek

# 롤아웃 상태 확인
kubectl rollout status deployment/agenticseek-api -n agenticseek

# 헬스체크
for i in {1..30}; do
    if curl -f https://app.company.com/health; then
        echo "✅ Rollback successful"
        exit 0
    fi
    echo "Waiting... ($i/30)"
    sleep 10
done

echo "❌ Rollback health check failed"
exit 1
```

---

## 8. 모니터링 및 알림

### 8.1 배포 모니터링

```yaml
# .github/workflows/deployment-monitor.yml

name: Deployment Monitor

on:
  schedule:
    - cron: '*/5 * * * *'  # 5분마다

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - name: Check production health
        run: |
          response=$(curl -s -o /dev/null -w "%{http_code}" https://app.company.com/health)
          if [ "$response" != "200" ]; then
            echo "❌ Production health check failed: HTTP $response"
            exit 1
          fi

      - name: Check error rate
        run: |
          # Prometheus 쿼리
          error_rate=$(curl -s "http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status=~\"5..\"}[5m])" | jq '.data.result[0].value[1]')

          if (( $(echo "$error_rate > 0.01" | bc -l) )); then
            echo "⚠️ High error rate detected: $error_rate"
            exit 1
          fi

      - name: Alert on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "🚨 Production Alert",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Production Issue Detected*\nPlease check the application immediately!"
                  }
                }
              ]
            }
```

### 8.2 알림 통합

```yaml
# .github/workflows/notifications.yml

name: Notifications

on:
  workflow_run:
    workflows: ["CI Pipeline", "CD Pipeline"]
    types:
      - completed

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - name: Slack Notification
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "Workflow ${{ github.event.workflow_run.name }}: ${{ github.event.workflow_run.conclusion }}",
              "attachments": [
                {
                  "color": "${{ github.event.workflow_run.conclusion == 'success' && 'good' || 'danger' }}",
                  "fields": [
                    {
                      "title": "Repository",
                      "value": "${{ github.repository }}",
                      "short": true
                    },
                    {
                      "title": "Branch",
                      "value": "${{ github.ref_name }}",
                      "short": true
                    }
                  ]
                }
              ]
            }

      - name: Email Notification
        if: failure()
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 587
          username: ${{ secrets.SMTP_USERNAME }}
          password: ${{ secrets.SMTP_PASSWORD }}
          subject: "⚠️ Build Failed: ${{ github.event.workflow_run.name }}"
          to: devops@company.com
          from: GitHub Actions
          body: |
            Workflow ${{ github.event.workflow_run.name }} failed.
            Repository: ${{ github.repository }}
            Branch: ${{ github.ref_name }}
            Commit: ${{ github.sha }}
```

---

## 부록: CI/CD 체크리스트

### 파이프라인 설정
- [ ] 린트 및 포맷팅 검사
- [ ] 단위 테스트 (커버리지 80% 이상)
- [ ] 통합 테스트
- [ ] 보안 스캔 (SAST, DAST, 의존성)
- [ ] Docker 이미지 빌드
- [ ] 이미지 취약점 스캔

### 배포 설정
- [ ] 스테이징 환경 자동 배포
- [ ] 프로덕션 배포 승인 프로세스
- [ ] 블루-그린 배포 전략
- [ ] 헬스체크 및 스모크 테스트
- [ ] 자동 롤백 메커니즘

### 모니터링
- [ ] 배포 상태 모니터링
- [ ] 에러율 추적
- [ ] 성능 메트릭 수집
- [ ] 알림 설정 (Slack, Email)

### 보안
- [ ] 시크릿 관리 (GitHub Secrets, Vault)
- [ ] API 키 로테이션
- [ ] 정기적인 보안 감사
- [ ] 취약점 자동 패치

---

**문서 버전**: 1.0
**최종 수정**: 2025-11-02
**작성자**: DevOps Team
