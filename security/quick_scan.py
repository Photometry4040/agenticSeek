#!/usr/bin/env python3
"""
Quick Vulnerability Assessment Script

Analyzes the current AgenticSeek codebase for security vulnerabilities
without requiring a running server.

This script checks:
1. Authentication implementation
2. CORS configuration
3. Code execution safety
4. Input validation
5. API key management
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

class VulnerabilityScanner:
    """Static code analysis for security vulnerabilities"""

    def __init__(self, project_root: str = "/home/user/agenticSeek"):
        self.project_root = Path(project_root)
        self.findings = []

    def scan_all(self) -> Dict:
        """Run all security checks"""
        print("=" * 70)
        print("🔍 AgenticSeek Vulnerability Assessment")
        print("=" * 70)
        print()

        results = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': []
        }

        # Check 1: Authentication
        auth_issues = self.check_authentication()
        results['critical'].extend(auth_issues)

        # Check 2: CORS
        cors_issues = self.check_cors()
        results['critical'].extend(cors_issues)

        # Check 3: Code Execution
        code_exec_issues = self.check_code_execution()
        results['critical'].extend(code_exec_issues)

        # Check 4: Shell Injection
        shell_issues = self.check_shell_injection()
        results['critical'].extend(shell_issues)

        # Check 5: Input Validation
        input_issues = self.check_input_validation()
        results['high'].extend(input_issues)

        # Check 6: API Keys
        api_key_issues = self.check_api_keys()
        results['high'].extend(api_key_issues)

        return results

    def check_authentication(self) -> List[Dict]:
        """Check for authentication implementation"""
        print("[*] Checking authentication...")
        issues = []

        api_file = self.project_root / "api.py"

        if api_file.exists():
            content = api_file.read_text()

            # Check for authentication middleware
            has_auth = any([
                'verify_api_key' in content,
                'APIKeyHeader' in content,
                'OAuth' in content,
                'JWT' in content
            ])

            if not has_auth:
                issues.append({
                    'severity': 'CRITICAL',
                    'title': 'No Authentication',
                    'file': 'api.py',
                    'description': 'No authentication mechanism found in API',
                    'impact': 'Anyone can access all endpoints',
                    'recommendation': 'Implement API key or JWT authentication'
                })
                print("  ❌ No authentication found")
            else:
                print("  ✅ Authentication implementation detected")

        return issues

    def check_cors(self) -> List[Dict]:
        """Check CORS configuration"""
        print("[*] Checking CORS configuration...")
        issues = []

        api_file = self.project_root / "api.py"

        if api_file.exists():
            content = api_file.read_text()

            # Check for allow_origins=["*"]
            if re.search(r'allow_origins\s*=\s*\[\s*["\']?\*["\']?\s*\]', content):
                issues.append({
                    'severity': 'CRITICAL',
                    'title': 'CORS Misconfiguration',
                    'file': 'api.py',
                    'description': 'CORS allows all origins (*)',
                    'impact': 'CSRF attacks possible from any domain',
                    'recommendation': 'Use whitelist of allowed origins'
                })
                print("  ❌ CORS allows all origins (*)")
            else:
                print("  ✅ CORS properly configured")

        return issues

    def check_code_execution(self) -> List[Dict]:
        """Check for unsafe code execution"""
        print("[*] Checking code execution safety...")
        issues = []

        py_interpreter = self.project_root / "sources" / "tools" / "PyInterpreter.py"

        if py_interpreter.exists():
            content = py_interpreter.read_text()

            # Check for exec() usage
            if 'exec(' in content:
                # Check if sandboxed
                has_sandbox = any([
                    'RestrictedPython' in content,
                    'compile_restricted' in content,
                    'safe_globals' in content
                ])

                if not has_sandbox:
                    issues.append({
                        'severity': 'CRITICAL',
                        'title': 'Arbitrary Code Execution',
                        'file': 'sources/tools/PyInterpreter.py',
                        'description': 'exec() used without sandbox',
                        'impact': 'Attackers can execute any Python code',
                        'recommendation': 'Use RestrictedPython or Docker sandbox'
                    })
                    print("  ❌ Unsafe exec() detected")
                else:
                    print("  ✅ Code execution is sandboxed")

        return issues

    def check_shell_injection(self) -> List[Dict]:
        """Check for shell injection vulnerabilities"""
        print("[*] Checking shell injection vulnerabilities...")
        issues = []

        bash_interpreter = self.project_root / "sources" / "tools" / "BashInterpreter.py"

        if bash_interpreter.exists():
            content = bash_interpreter.read_text()

            # Check for shell=True
            if re.search(r'shell\s*=\s*True', content):
                issues.append({
                    'severity': 'CRITICAL',
                    'title': 'Shell Injection',
                    'file': 'sources/tools/BashInterpreter.py',
                    'description': 'subprocess uses shell=True',
                    'impact': 'Command injection attacks possible',
                    'recommendation': 'Use shell=False and shlex.split()'
                })
                print("  ❌ shell=True detected")
            else:
                print("  ✅ Shell injection prevented")

        return issues

    def check_input_validation(self) -> List[Dict]:
        """Check for input validation"""
        print("[*] Checking input validation...")
        issues = []

        api_file = self.project_root / "api.py"

        if api_file.exists():
            content = api_file.read_text()

            # Check for validation
            has_validation = any([
                'validate_query' in content,
                'sanitize' in content,
                '@validator' in content
            ])

            if not has_validation:
                issues.append({
                    'severity': 'HIGH',
                    'title': 'No Input Validation',
                    'file': 'api.py',
                    'description': 'User input not validated',
                    'impact': 'Prompt injection and XSS possible',
                    'recommendation': 'Add input validation and sanitization'
                })
                print("  ❌ No input validation found")
            else:
                print("  ✅ Input validation detected")

        return issues

    def check_api_keys(self) -> List[Dict]:
        """Check API key security"""
        print("[*] Checking API key security...")
        issues = []

        # Check for hardcoded secrets
        searxng_settings = self.project_root / "searxng" / "settings.yml"

        if searxng_settings.exists():
            content = searxng_settings.read_text()

            if 'supersecret' in content.lower():
                issues.append({
                    'severity': 'HIGH',
                    'title': 'Hardcoded Secret',
                    'file': 'searxng/settings.yml',
                    'description': 'Secret key hardcoded in configuration',
                    'impact': 'Secret exposed in version control',
                    'recommendation': 'Use environment variables'
                })
                print("  ❌ Hardcoded secret found")

        return issues

    def print_report(self, results: Dict):
        """Print vulnerability report"""
        print()
        print("=" * 70)
        print("📊 Vulnerability Assessment Report")
        print("=" * 70)
        print()

        total = sum(len(issues) for issues in results.values())

        if total == 0:
            print("✅ No vulnerabilities found!")
            return

        for severity in ['critical', 'high', 'medium', 'low']:
            issues = results[severity]
            if not issues:
                continue

            emoji = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🔵'
            }[severity]

            print(f"{emoji} {severity.upper()} ({len(issues)} issues)")
            print("-" * 70)

            for i, issue in enumerate(issues, 1):
                print(f"\n{i}. {issue['title']}")
                print(f"   File: {issue['file']}")
                print(f"   Description: {issue['description']}")
                print(f"   Impact: {issue['impact']}")
                print(f"   ✅ Fix: {issue['recommendation']}")

            print()

        print("=" * 70)
        print(f"Total Issues: {total}")
        print("=" * 70)
        print()
        print("📋 Next Steps:")
        print("1. Apply security patches from security/patches/")
        print("2. Follow deployment guide in security/README.md")
        print("3. Run penetration test to verify fixes")
        print()


def main():
    """Main function"""
    scanner = VulnerabilityScanner()
    results = scanner.scan_all()
    scanner.print_report(results)

    # Return exit code based on findings
    critical_count = len(results['critical'])
    if critical_count > 0:
        print(f"⚠️  Found {critical_count} CRITICAL vulnerabilities")
        print("❌ System is NOT safe for production use")
        return 1
    else:
        print("✅ No critical vulnerabilities detected")
        return 0


if __name__ == "__main__":
    exit(main())
