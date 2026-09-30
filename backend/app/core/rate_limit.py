from slowapi import Limiter
from slowapi.util import get_remote_address

# IP-based rate limiting. Keeps a single free-tier Groq key / small VPS
# from being hammered by one client, and is a standard example of API
# hardening that reviewers expect on a "production" project.
limiter = Limiter(key_func=get_remote_address)
