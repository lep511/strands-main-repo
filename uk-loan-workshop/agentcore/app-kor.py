#!/usr/bin/env python3
"""
Chat Frontend for AgentCore Runtime Loan Orchestrator — Korean UI (한국어).

app.py와 동일한 애플리케이션을 한국어 UI로 실행하고, 오케스트레이터에
language='ko'를 전달해 응답도 한국어로 생성되도록 합니다.
(오케스트레이터는 한국어용으로 수정된 시스템 프롬프트를 사용합니다.)

Run: python3 app-kor.py
Then open: http://localhost:3000
"""
import app

app.set_language('ko')

if __name__ == '__main__':
    print("\n🏦 영국 대출 도우미 채팅 (한국어)")
    print(f"   Runtime ARN: {app.RUNTIME_ARN}")
    print("   Open: http://localhost:3000\n")
    app.app.run(host='0.0.0.0', port=3000, debug=False)
