#!/bin/bash
cd /home/kavia/workspace/code-generation/visitor-check-in-assistant-100434-100452/visitor_management_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

