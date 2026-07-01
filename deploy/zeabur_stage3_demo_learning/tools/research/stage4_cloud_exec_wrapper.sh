#!/bin/sh
# Pass Zeabur shell-injected Groq secrets to Python children via explicit env(1).
set -e
cd /app
exec env \
  ${GROQ_API_KEY:+GROQ_API_KEY=$GROQ_API_KEY} \
  ${GROQ_API_KEY_PRIMARY:+GROQ_API_KEY_PRIMARY=$GROQ_API_KEY_PRIMARY} \
  ${GROQ_API_KEY_SECONDARY:+GROQ_API_KEY_SECONDARY=$GROQ_API_KEY_SECONDARY} \
  "$@"
