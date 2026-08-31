#!/usr/bin/env python3
"""
AgentPay End-to-End System & API Verification Script
Tests frontend, backend health, policy engine, wallets, merchants, and agent orchestration.
"""

import sys
import json
import urllib.request
import urllib.error

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:5173"


def http_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "AgentPay-Tester"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            content = response.read().decode("utf-8")
            try:
                data = json.loads(content)
            except Exception:
                data = content
            return status, data
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            data = json.loads(content)
        except Exception:
            data = content
        return e.code, data
    except Exception as e:
        return 0, str(e)


def http_post(url: str, payload: dict):
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "AgentPay-Tester"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            status = response.status
            content = response.read().decode("utf-8")
            try:
                data = json.loads(content)
            except Exception:
                data = content
            return status, data
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            data = json.loads(content)
        except Exception:
            data = content
        return e.code, data
    except Exception as e:
        return 0, str(e)


def run_system_test():
    print("=" * 70)
    print("🧪 AGENTPAY FULL STACK SYSTEM & SAMPLE API TEST")
    print("=" * 70)

    passed = 0
    total = 0

    # 1. Frontend Connectivity Test
    total += 1
    print("\n[1] Testing Frontend Server (http://localhost:5173)...")
    status, res = http_get(FRONTEND_URL)
    if status == 200:
        print("  ✓ Frontend is reachable (HTTP 200 OK)")
        passed += 1
    else:
        print(f"  ❌ Frontend check failed (Status {status}): {res}")

    # 2. Backend Root Endpoint
    total += 1
    print("\n[2] Testing Backend Root Endpoint (http://127.0.0.1:8000/)...")
    status, res = http_get(f"{BACKEND_URL}/")
    if status == 200 and isinstance(res, dict) and "app" in res:
        print(f"  ✓ Backend Root is active: {res.get('app')} - {res.get('message')}")
        passed += 1
    else:
        print(f"  ❌ Backend Root failed (Status {status}): {res}")

    # 3. Backend Health & Database Connection
    total += 1
    print("\n[3] Testing Backend Health Endpoint (http://127.0.0.1:8000/health)...")
    status, res = http_get(f"{BACKEND_URL}/health")
    if status == 200 and isinstance(res, dict) and res.get("database") == "connected":
        print(f"  ✓ Backend Health status: {res.get('status')} | Database: {res.get('database')}")
        passed += 1
    else:
        print(f"  ❌ Backend Health failed (Status {status}): {res}")

    # 4. Backend Swagger Docs
    total += 1
    print("\n[4] Testing Interactive Swagger Docs (http://127.0.0.1:8000/docs)...")
    status, res = http_get(f"{BACKEND_URL}/docs")
    if status == 200:
        print("  ✓ Interactive API Docs (/docs) accessible")
        passed += 1
    else:
        print(f"  ❌ Docs endpoint failed (Status {status})")

    # 5. Sample API: Get Wallet Details
    total += 1
    print("\n[5] Testing Wallet API (GET /api/wallet)...")
    status, res = http_get(f"{BACKEND_URL}/api/wallet")
    if status == 200 and isinstance(res, dict):
        print(f"  ✓ Wallet active! Currency: {res.get('currency')} | Daily Budget: ₹{res.get('daily_spending_limit')}")
        passed += 1
    else:
        print(f"  ❌ Wallet API failed (Status {status}): {res}")

    # 6. Sample API: Get Registered Merchants
    total += 1
    print("\n[6] Testing Merchants API (GET /api/merchants)...")
    status, res = http_get(f"{BACKEND_URL}/api/merchants")
    if status == 200 and isinstance(res, list) and len(res) > 0:
        print(f"  ✓ Merchants retrieved ({len(res)} merchants found): {[m.get('name') for m in res[:3]]}...")
        passed += 1
    else:
        print(f"  ❌ Merchants API failed (Status {status}): {res}")

    # 7. Sample API: AI Agent Orchestration (Allowed Flow)
    total += 1
    print("\n[7] Testing AI Agent Orchestrator API (POST /api/agent/run - Electricity Bill)...")
    payload_allow = {
        "message": "Please pay my electricity bill of 1240 for Torrent Power",
        "merchant_name": "Torrent Power",
        "amount": 1240.0,
        "category": "utilities",
    }
    status, res = http_post(f"{BACKEND_URL}/api/agent/run", payload_allow)
    if status == 200 and isinstance(res, dict) and res.get("decision") == "ALLOWED":
        print(f"  ✓ Agent Orchestration Decision: {res.get('decision')} | Payment Status: {res.get('payment_status')}")
        print(f"    Payment ID: {res.get('payment_id')} | Provider ID: {res.get('provider_payment_id')}")
        passed += 1
    else:
        print(f"  ❌ Agent API failed (Status {status}): {res}")

    # 8. Sample API: AI Agent Orchestration (Policy Denied Flow)
    total += 1
    print("\n[8] Testing AI Agent Policy Denied API (POST /api/agent/run - ₹99,999 Over Limit)...")
    payload_deny = {
        "message": "Pay luxury electronics purchase of 99999",
        "merchant_name": "Apple Store",
        "amount": 99999.0,
        "category": "electronics",
    }
    status, res = http_post(f"{BACKEND_URL}/api/agent/run", payload_deny)
    if status == 200 and isinstance(res, dict) and res.get("decision") == "DENIED":
        print(f"  ✓ Correctly Denied by Policy Engine: {res.get('decision_code')}")
        print(f"    Message: {res.get('message')}")
        passed += 1
    else:
        print(f"  ❌ Expected DENIED but got (Status {status}): {res}")

    # Summary
    print("\n" + "=" * 70)
    print(f"📊 TEST RESULTS: {passed}/{total} Tests Passed Successfully!")
    print("=" * 70)

    if passed == total:
        print("🎉 Full stack (Frontend, Backend, Database, APIs) is working 100% properly!")
        return 0
    else:
        print("⚠️ Some tests failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_system_test())
