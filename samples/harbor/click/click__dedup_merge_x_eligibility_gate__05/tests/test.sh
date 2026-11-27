#!/bin/bash
# Harbor runs this after the agent has finished. It writes /logs/verifier/reward.txt.
mkdir -p /logs/verifier
cd /app
/usr/local/bin/python /tests/grade.py --app /app --tests /tests --out /logs/verifier
