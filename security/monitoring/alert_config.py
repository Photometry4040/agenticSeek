"""
Security Monitoring and Alerting Configuration

Monitors security events and sends alerts via multiple channels:
- Email
- Slack
- SMS (via Twilio)
- Webhook

Usage:
    from security.monitoring.alert_config import SecurityMonitor

    monitor = SecurityMonitor()
    monitor.alert_authentication_failure(ip="192.168.1.100", attempts=5)
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("security_monitor")

class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertChannel(Enum):
    """Alert delivery channels"""
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    WEBHOOK = "webhook"
    LOG = "log"

class SecurityMonitor:
    """Security event monitoring and alerting"""

    def __init__(self):
        """Initialize security monitor"""
        self.config = self._load_config()
        self.event_history = []
        self.alert_history = []

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('.logs/security_events.log'),
                logging.StreamHandler()
            ]
        )

    def _load_config(self) -> Dict:
        """Load configuration from environment"""
        return {
            'email': {
                'enabled': os.getenv('ALERT_EMAIL_ENABLED', 'false').lower() == 'true',
                'smtp_server': os.getenv('ALERT_SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('ALERT_SMTP_PORT', '587')),
                'from_email': os.getenv('ALERT_FROM_EMAIL', 'security@company.com'),
                'to_emails': os.getenv('ALERT_TO_EMAILS', '').split(','),
                'password': os.getenv('ALERT_EMAIL_PASSWORD', '')
            },
            'slack': {
                'enabled': os.getenv('ALERT_SLACK_ENABLED', 'false').lower() == 'true',
                'webhook_url': os.getenv('ALERT_SLACK_WEBHOOK', '')
            },
            'sms': {
                'enabled': os.getenv('ALERT_SMS_ENABLED', 'false').lower() == 'true',
                'twilio_sid': os.getenv('TWILIO_ACCOUNT_SID', ''),
                'twilio_token': os.getenv('TWILIO_AUTH_TOKEN', ''),
                'from_number': os.getenv('TWILIO_FROM_NUMBER', ''),
                'to_numbers': os.getenv('ALERT_TO_NUMBERS', '').split(',')
            },
            'thresholds': {
                'auth_failures': int(os.getenv('ALERT_AUTH_FAILURES_THRESHOLD', '5')),
                'rate_limit_hits': int(os.getenv('ALERT_RATE_LIMIT_THRESHOLD', '10')),
                'code_exec_failures': int(os.getenv('ALERT_CODE_EXEC_THRESHOLD', '3'))
            }
        }

    def log_event(self, event_type: str, details: Dict):
        """
        Log security event

        Args:
            event_type: Type of security event
            details: Event details
        """
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': event_type,
            'details': details
        }

        self.event_history.append(event)
        logger.info(f"Security event: {event_type} - {json.dumps(details)}")

    def send_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        details: Optional[Dict] = None,
        channels: Optional[List[AlertChannel]] = None
    ):
        """
        Send security alert

        Args:
            severity: Alert severity level
            title: Alert title
            message: Alert message
            details: Additional details
            channels: Alert channels to use
        """
        # Default to all enabled channels
        if channels is None:
            channels = self._get_enabled_channels()

        alert = {
            'timestamp': datetime.utcnow().isoformat(),
            'severity': severity.value,
            'title': title,
            'message': message,
            'details': details or {}
        }

        self.alert_history.append(alert)

        # Log alert
        logger.warning(f"SECURITY ALERT [{severity.value.upper()}]: {title} - {message}")

        # Send via each channel
        for channel in channels:
            try:
                if channel == AlertChannel.EMAIL:
                    self._send_email_alert(alert)
                elif channel == AlertChannel.SLACK:
                    self._send_slack_alert(alert)
                elif channel == AlertChannel.SMS:
                    self._send_sms_alert(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel.value}: {e}")

    def _get_enabled_channels(self) -> List[AlertChannel]:
        """Get list of enabled alert channels"""
        channels = [AlertChannel.LOG]  # Always log

        if self.config['email']['enabled']:
            channels.append(AlertChannel.EMAIL)
        if self.config['slack']['enabled']:
            channels.append(AlertChannel.SLACK)
        if self.config['sms']['enabled']:
            channels.append(AlertChannel.SMS)

        return channels

    def _send_email_alert(self, alert: Dict):
        """Send email alert"""
        if not self.config['email']['enabled']:
            return

        msg = MIMEMultipart()
        msg['From'] = self.config['email']['from_email']
        msg['To'] = ', '.join(self.config['email']['to_emails'])
        msg['Subject'] = f"[{alert['severity'].upper()}] {alert['title']}"

        body = f"""
Security Alert - AgenticSeek

Severity: {alert['severity'].upper()}
Time: {alert['timestamp']}
Title: {alert['title']}

Message:
{alert['message']}

Details:
{json.dumps(alert['details'], indent=2)}

---
This is an automated security alert from AgenticSeek.
"""

        msg.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP(
                self.config['email']['smtp_server'],
                self.config['email']['smtp_port']
            )
            server.starttls()
            server.login(
                self.config['email']['from_email'],
                self.config['email']['password']
            )
            server.send_message(msg)
            server.quit()
            logger.info("Email alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def _send_slack_alert(self, alert: Dict):
        """Send Slack alert"""
        if not self.config['slack']['enabled']:
            return

        import requests

        color_map = {
            'low': '#36a64f',
            'medium': '#ff9900',
            'high': '#ff6600',
            'critical': '#ff0000'
        }

        payload = {
            "attachments": [{
                "color": color_map.get(alert['severity'], '#808080'),
                "title": f"🚨 {alert['title']}",
                "text": alert['message'],
                "fields": [
                    {
                        "title": "Severity",
                        "value": alert['severity'].upper(),
                        "short": True
                    },
                    {
                        "title": "Time",
                        "value": alert['timestamp'],
                        "short": True
                    }
                ],
                "footer": "AgenticSeek Security Monitor",
                "ts": int(datetime.utcnow().timestamp())
            }]
        }

        try:
            response = requests.post(
                self.config['slack']['webhook_url'],
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            logger.info("Slack alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def _send_sms_alert(self, alert: Dict):
        """Send SMS alert"""
        if not self.config['sms']['enabled']:
            return

        try:
            from twilio.rest import Client

            client = Client(
                self.config['sms']['twilio_sid'],
                self.config['sms']['twilio_token']
            )

            message_body = f"[{alert['severity'].upper()}] {alert['title']}: {alert['message']}"

            for to_number in self.config['sms']['to_numbers']:
                if to_number:
                    client.messages.create(
                        body=message_body,
                        from_=self.config['sms']['from_number'],
                        to=to_number
                    )

            logger.info("SMS alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}")

    # Predefined alert methods
    def alert_authentication_failure(self, ip: str, attempts: int, user: Optional[str] = None):
        """Alert on authentication failures"""
        if attempts >= self.config['thresholds']['auth_failures']:
            self.send_alert(
                severity=AlertSeverity.HIGH,
                title="Multiple Authentication Failures",
                message=f"{attempts} failed authentication attempts detected",
                details={
                    'ip': ip,
                    'attempts': attempts,
                    'user': user,
                    'action': 'Consider blocking IP address'
                }
            )

    def alert_rate_limit_exceeded(self, ip: str, endpoint: str, count: int):
        """Alert on rate limit violations"""
        if count >= self.config['thresholds']['rate_limit_hits']:
            self.send_alert(
                severity=AlertSeverity.MEDIUM,
                title="Rate Limit Exceeded",
                message=f"IP {ip} exceeded rate limit on {endpoint}",
                details={
                    'ip': ip,
                    'endpoint': endpoint,
                    'count': count,
                    'action': 'Possible DoS attempt'
                }
            )

    def alert_code_execution_failure(self, code_hash: str, error: str):
        """Alert on suspicious code execution failures"""
        self.send_alert(
            severity=AlertSeverity.MEDIUM,
            title="Code Execution Failure",
            message=f"Code execution failed: {error}",
            details={
                'code_hash': code_hash,
                'error': error,
                'action': 'Review code for malicious patterns'
            }
        )

    def alert_suspicious_input(self, input_hash: str, patterns: List[str]):
        """Alert on suspicious input patterns"""
        self.send_alert(
            severity=AlertSeverity.HIGH,
            title="Suspicious Input Detected",
            message=f"Input matched {len(patterns)} dangerous pattern(s)",
            details={
                'input_hash': input_hash,
                'patterns': patterns,
                'action': 'Possible attack attempt'
            }
        )

    def alert_api_key_compromise(self, key_prefix: str, ip: str):
        """Alert on potential API key compromise"""
        self.send_alert(
            severity=AlertSeverity.CRITICAL,
            title="Potential API Key Compromise",
            message=f"API key {key_prefix}*** used from unusual IP",
            details={
                'key_prefix': key_prefix,
                'ip': ip,
                'action': 'REVOKE KEY IMMEDIATELY'
            },
            channels=[AlertChannel.EMAIL, AlertChannel.SMS, AlertChannel.SLACK]
        )

    def get_event_summary(self, hours: int = 24) -> Dict:
        """Get summary of events in the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        recent_events = [
            event for event in self.event_history
            if datetime.fromisoformat(event['timestamp']) > cutoff
        ]

        summary = {
            'total_events': len(recent_events),
            'by_type': {},
            'period_hours': hours
        }

        for event in recent_events:
            event_type = event['type']
            summary['by_type'][event_type] = summary['by_type'].get(event_type, 0) + 1

        return summary


# Example configuration for .env
EXAMPLE_ENV_CONFIG = """
# Security Monitoring Configuration

# Email Alerts
ALERT_EMAIL_ENABLED=true
ALERT_SMTP_SERVER=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_FROM_EMAIL=security@company.com
ALERT_TO_EMAILS=admin1@company.com,admin2@company.com
ALERT_EMAIL_PASSWORD=your-app-password

# Slack Alerts
ALERT_SLACK_ENABLED=true
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# SMS Alerts (Twilio)
ALERT_SMS_ENABLED=true
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_FROM_NUMBER=+1234567890
ALERT_TO_NUMBERS=+1234567890,+0987654321

# Alert Thresholds
ALERT_AUTH_FAILURES_THRESHOLD=5
ALERT_RATE_LIMIT_THRESHOLD=10
ALERT_CODE_EXEC_THRESHOLD=3
"""


if __name__ == "__main__":
    # Example usage
    print("Security Monitoring Configuration")
    print("=" * 70)
    print("\nAdd this to your .env file:")
    print(EXAMPLE_ENV_CONFIG)

    # Test monitor
    monitor = SecurityMonitor()

    # Simulate events
    print("\n" + "=" * 70)
    print("Testing alerts...")
    print("=" * 70 + "\n")

    monitor.alert_authentication_failure(ip="192.168.1.100", attempts=5)
    monitor.alert_suspicious_input(
        input_hash="abc123",
        patterns=["exec(", "rm -rf"]
    )

    # Get summary
    summary = monitor.get_event_summary()
    print("\nEvent Summary:")
    print(json.dumps(summary, indent=2))
