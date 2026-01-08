#!/bin/bash
python bot.py &      # 1. 봇을 먼저 백그라운드에서 실행 (스크립트 1)
gunicorn app:app --bind 0.0.0.0:$PORT  # 2. 웹 서버를 실행 (스크립트 2)