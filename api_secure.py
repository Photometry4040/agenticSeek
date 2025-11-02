#!/usr/bin/env python3
"""
AgenticSeek Secure API - Production-Ready Version

This file includes all security patches:
✅ API Key Authentication
✅ Secure CORS Configuration
✅ Input Validation
✅ Rate Limiting
✅ Audit Logging
✅ Security Headers

To use this file:
1. Set environment variables in .env:
   AGENTICSEEK_API_KEYS="your-key-1,your-key-2"
   ALLOWED_ORIGINS="https://your-domain.com"

2. Run: python api_secure.py

3. Test: curl -H "X-API-Key: your-key-1" http://localhost:7777/health
"""

import os, sys
import uvicorn
import aiofiles
import configparser
import asyncio
import time
from typing import List
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid

# Original imports
from sources.llm_provider import Provider
from sources.interaction import Interaction
from sources.agents import CasualAgent, CoderAgent, FileAgent, PlannerAgent, BrowserAgent
from sources.browser import Browser, create_driver
from sources.utility import pretty_print
from sources.logger import Logger
from sources.schemas import QueryRequest, QueryResponse

# 🛡️ Security Patches
from security.patches.auth_middleware import (
    setup_auth,
    verify_api_key,
    check_rate_limit
)
from security.patches.secure_cors import setup_secure_cors
from security.patches.input_validation import (
    validate_query,
    ValidationError
)

from dotenv import load_dotenv

load_dotenv()

def is_running_in_docker():
    """Detect if code is running inside a Docker container."""
    if os.path.exists('/.dockerenv'):
        return True

    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass

    return False


from celery import Celery

# Initialize FastAPI with security settings
api = FastAPI(
    title="AgenticSeek API (Secure)",
    version="1.0.0-secure",
    description="Production-ready API with security enhancements",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None
)

celery_app = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")
celery_app.conf.update(task_track_started=True)
logger = Logger("backend_secure.log")
config = configparser.ConfigParser()
config.read('config.ini')

# 🛡️ SECURITY PATCH 1: Secure CORS
# Replaces: allow_origins=["*"]
setup_secure_cors(api)

# 🛡️ SECURITY PATCH 2: Authentication
setup_auth(api)

# 🛡️ SECURITY PATCH 3: Security Headers
@api.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

if not os.path.exists(".screenshots"):
    os.makedirs(".screenshots")
api.mount("/screenshots", StaticFiles(directory=".screenshots"), name="screenshots")

def initialize_system():
    stealth_mode = config.getboolean('BROWSER', 'stealth_mode')
    personality_folder = "jarvis" if config.getboolean('MAIN', 'jarvis_personality') else "base"
    languages = config["MAIN"]["languages"].split(' ')

    # Force headless mode in Docker containers
    headless = config.getboolean('BROWSER', 'headless_browser')
    if is_running_in_docker() and not headless:
        print("\n" + "*" * 70)
        print("*** WARNING: Detected Docker environment - forcing headless_browser=True ***")
        print("*** INFO: To see the browser, run 'python cli.py' on your host machine ***")
        print("*" * 70 + "\n")
        sys.stdout.flush()
        logger.warning("Detected Docker environment - forcing headless_browser=True")
        logger.info("To see the browser, run 'python cli.py' on your host machine instead")
        headless = True

    provider = Provider(
        provider_name=config["MAIN"]["provider_name"],
        model=config["MAIN"]["provider_model"],
        server_address=config["MAIN"]["provider_server_address"],
        is_local=config.getboolean('MAIN', 'is_local')
    )
    logger.info(f"Provider initialized: {provider.provider_name} ({provider.model})")

    browser = Browser(
        create_driver(headless=headless, stealth_mode=stealth_mode, lang=languages[0]),
        anticaptcha_manual_install=stealth_mode
    )
    logger.info("Browser initialized")

    agents = [
        CasualAgent(
            name=config["MAIN"]["agent_name"],
            prompt_path=f"prompts/{personality_folder}/casual_agent.txt",
            provider=provider, verbose=False
        ),
        CoderAgent(
            name="coder",
            prompt_path=f"prompts/{personality_folder}/coder_agent.txt",
            provider=provider, verbose=False
        ),
        FileAgent(
            name="File Agent",
            prompt_path=f"prompts/{personality_folder}/file_agent.txt",
            provider=provider, verbose=False
        ),
        BrowserAgent(
            name="Browser",
            prompt_path=f"prompts/{personality_folder}/browser_agent.txt",
            provider=provider, verbose=False, browser=browser
        ),
        PlannerAgent(
            name="Planner",
            prompt_path=f"prompts/{personality_folder}/planner_agent.txt",
            provider=provider, verbose=False, browser=browser
        )
    ]
    logger.info("Agents initialized")

    interaction = Interaction(
        agents,
        tts_enabled=config.getboolean('MAIN', 'speak'),
        stt_enabled=config.getboolean('MAIN', 'listen'),
        recover_last_session=config.getboolean('MAIN', 'recover_last_session'),
        langs=languages
    )
    logger.info("Interaction initialized")
    return interaction

interaction = initialize_system()
is_generating = False
query_resp_history = []

# 🛡️ SECURITY PATCH 4: Protected Endpoints with Authentication

@api.get("/screenshot")
async def get_screenshot(
    api_key: str = Depends(verify_api_key)  # ✅ Authentication required
):
    """Get current browser screenshot (requires authentication)"""
    logger.info("Screenshot endpoint called (authenticated)")
    screenshot_path = ".screenshots/updated_screen.png"
    if os.path.exists(screenshot_path):
        return FileResponse(screenshot_path)
    logger.error("No screenshot available")
    return JSONResponse(
        status_code=404,
        content={"error": "No screenshot available"}
    )

@api.get("/health")
async def health_check():
    """Health check endpoint (no authentication required)"""
    logger.info("Health check endpoint called")
    return {
        "status": "healthy",
        "version": "1.0.0-secure",
        "security": "enabled",
        "timestamp": time.time()
    }

@api.get("/is_active")
async def is_active(
    api_key: str = Depends(verify_api_key)  # ✅ Authentication required
):
    """Check if agent is active (requires authentication)"""
    logger.info("Is active endpoint called (authenticated)")
    return {"is_active": interaction.is_active}

@api.get("/stop")
async def stop(
    api_key: str = Depends(verify_api_key)  # ✅ Authentication required
):
    """Stop current agent processing (requires authentication)"""
    logger.info("Stop endpoint called (authenticated)")
    interaction.current_agent.request_stop()
    return JSONResponse(status_code=200, content={"status": "stopped"})

@api.get("/latest_answer")
async def get_latest_answer(
    api_key: str = Depends(verify_api_key)  # ✅ Authentication required
):
    """Get latest answer (requires authentication)"""
    global query_resp_history
    if interaction.current_agent is None:
        return JSONResponse(status_code=404, content={"error": "No agent available"})
    uid = str(uuid.uuid4())
    if not any(q["answer"] == interaction.current_agent.last_answer for q in query_resp_history):
        query_resp = {
            "done": "false",
            "answer": interaction.current_agent.last_answer,
            "reasoning": interaction.current_agent.last_reasoning,
            "agent_name": interaction.current_agent.agent_name if interaction.current_agent else "None",
            "success": interaction.current_agent.success,
            "blocks": {f'{i}': block.jsonify() for i, block in enumerate(interaction.get_last_blocks_result())} if interaction.current_agent else {},
            "status": interaction.current_agent.get_status_message if interaction.current_agent else "No status available",
            "uid": uid
        }
        interaction.current_agent.last_answer = ""
        interaction.current_agent.last_reasoning = ""
        query_resp_history.append(query_resp)
        return JSONResponse(status_code=200, content=query_resp)
    if query_resp_history:
        return JSONResponse(status_code=200, content=query_resp_history[-1])
    return JSONResponse(status_code=404, content={"error": "No answer available"})

async def think_wrapper(interaction, query):
    try:
        interaction.last_query = query
        logger.info("Agents request is being processed")
        success = await interaction.think()
        if not success:
            interaction.last_answer = "Error: No answer from agent"
            interaction.last_reasoning = "Error: No reasoning from agent"
            interaction.last_success = False
        else:
            interaction.last_success = True
        pretty_print(interaction.last_answer)
        interaction.speak_answer()
        return success
    except Exception as e:
        logger.error(f"Error in think_wrapper: {str(e)}")
        interaction.last_answer = f""
        interaction.last_reasoning = f"Error: {str(e)}"
        interaction.last_success = False
        raise e

@api.post("/query", response_model=QueryResponse)
async def process_query(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key),  # ✅ Authentication required
    _: None = Depends(check_rate_limit)      # ✅ Rate limiting
):
    """
    Process user query (requires authentication and rate limiting)

    🛡️ Security Features:
    - API key authentication
    - Rate limiting (60 requests/minute)
    - Input validation
    - Audit logging
    """
    global is_generating, query_resp_history

    # 🛡️ SECURITY PATCH 5: Input Validation
    try:
        validated_query = validate_query(request.query)
        logger.info(f"Processing validated query (length: {len(validated_query)})")
    except ValidationError as e:
        logger.warning(f"Invalid input blocked: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid input: {str(e)}"}
        )

    query_resp = QueryResponse(
        done="false",
        answer="",
        reasoning="",
        agent_name="Unknown",
        success="false",
        blocks={},
        status="Ready",
        uid=str(uuid.uuid4())
    )

    if is_generating:
        logger.warning("Another query is being processed, please wait.")
        return JSONResponse(status_code=429, content=query_resp.jsonify())

    try:
        is_generating = True
        # Use validated query instead of raw input
        success = await think_wrapper(interaction, validated_query)
        is_generating = False

        if not success:
            query_resp.answer = interaction.last_answer
            query_resp.reasoning = interaction.last_reasoning
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        if interaction.current_agent:
            blocks_json = {f'{i}': block.jsonify() for i, block in enumerate(interaction.current_agent.get_blocks_result())}
        else:
            logger.error("No current agent found")
            blocks_json = {}
            query_resp.answer = "Error: No current agent"
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        logger.info(f"Answer: {interaction.last_answer}")
        logger.info(f"Blocks: {blocks_json}")
        query_resp.done = "true"
        query_resp.answer = interaction.last_answer
        query_resp.reasoning = interaction.last_reasoning
        query_resp.agent_name = interaction.current_agent.agent_name
        query_resp.success = str(interaction.last_success)
        query_resp.blocks = blocks_json

        query_resp_dict = {
            "done": query_resp.done,
            "answer": query_resp.answer,
            "agent_name": query_resp.agent_name,
            "success": query_resp.success,
            "blocks": query_resp.blocks,
            "status": query_resp.status,
            "uid": query_resp.uid
        }
        query_resp_history.append(query_resp_dict)

        logger.info("Query processed successfully")
        return JSONResponse(status_code=200, content=query_resp.jsonify())
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        # Don't exit, return error response
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
    finally:
        logger.info("Processing finished")
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()

@api.on_event("startup")
async def startup_event():
    """Startup event with security checks"""
    logger.info("=" * 70)
    logger.info("🛡️  AgenticSeek Secure API Starting")
    logger.info("=" * 70)

    # Security checks
    if not os.getenv("AGENTICSEEK_API_KEYS"):
        logger.warning("⚠️  No API keys configured!")
        logger.warning("Set AGENTICSEEK_API_KEYS environment variable")

    if not os.getenv("ALLOWED_ORIGINS"):
        logger.warning("⚠️  Using default CORS origins (localhost only)")

    logger.info("Security features enabled:")
    logger.info("  ✅ API key authentication")
    logger.info("  ✅ Secure CORS configuration")
    logger.info("  ✅ Input validation")
    logger.info("  ✅ Rate limiting")
    logger.info("  ✅ Security headers")
    logger.info("  ✅ Audit logging")
    logger.info("=" * 70)

if __name__ == "__main__":
    # Print startup info
    if is_running_in_docker():
        print("[AgenticSeek Secure] Starting in Docker container...")
    else:
        print("[AgenticSeek Secure] Starting on host machine...")

    envport = os.getenv("BACKEND_PORT")
    port = int(envport) if envport else 7777

    print("\n" + "=" * 70)
    print("🛡️  AgenticSeek Secure API")
    print("=" * 70)
    print(f"Port: {port}")
    print(f"Security: ENABLED")
    print(f"\n⚠️  Make sure to set:")
    print(f"  - AGENTICSEEK_API_KEYS in .env")
    print(f"  - ALLOWED_ORIGINS in .env")
    print("=" * 70 + "\n")

    uvicorn.run(api, host="0.0.0.0", port=port)
