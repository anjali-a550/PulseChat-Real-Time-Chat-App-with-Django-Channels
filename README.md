✨ Features
Feature	Description
⚡ Live messaging	Messages are sent over WebSockets, saved to the database and broadcast to everyone in the room
🏠 Rooms	Three seeded rooms (#general, #python, #random); any user can create more
🔒 Direct messages	Private 1:1 rooms that outsiders can't open over HTTP or WebSocket
🟢 Presence	See who is online in the current room, updated on every join and leave
⌨️ Typing indicator	"Meera is typing…", never echoed back to the person typing
🔴 Unread badges	Per-room and per-DM unread counts, computed in a single SQL query
🛡️ Moderation	Blocked words are masked (******) and the message is tagged Moderated
🚦 Rate limiting	5 messages per 5 seconds per connection (configurable)
📜 History paging	"Load older messages" through a JSON API
🔁 Auto-reconnect	Exponential backoff (1 s → 15 s) with a Live / Offline status badge
📱 Responsive UI	Slide-out sidebar on phones, plus light and dark themes
🧰 Tech stack
Layer	Technology
Backend	Python 3.12, Django 5.1, Django Channels 4
ASGI server	Daphne
Real-time broker	Redis (channels-redis)
Database	PostgreSQL 16 (Docker) / SQLite (local dev)
Frontend	Django templates, vanilla JavaScript, CSS
DevOps	Docker Compose, GitHub Actions CI, WhiteNoise
🏗️ Architecture
HTTP
WebSocket
① rate limit + moderate② save
③ group_send
④ deliver to everysocket in the room
⑤ send_json
Browser A
Django views
ChatConsumer (sender)
PostgreSQL
Redis channel layer
ChatConsumer (receiver)
Browser B

Daphne serves both HTTP and WebSockets. When a user sends a message, their ChatConsumer validates it, saves it, and publishes it to the room's group. Redis then delivers it to every consumer in that group, on any server process, and each consumer pushes it to its own browser.

🚀 Getting started
Prerequisites
Python 3.12+
Git
Docker Desktop (optional, only for the PostgreSQL + Redis setup)
Option 1: Run locally (no Docker)
bash
git clone https://github.com/anjali-a550/pulsechat.git
cd pulsechat

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate           # also creates #general, #python, #random
python manage.py createsuperuser   # optional, for /admin
python manage.py runserver

Open http://127.0.0.1:8000 and sign up. To see real-time chat, open a private/incognito window, sign up as a second user, and chat between the two.

Locally the app uses SQLite and an in-memory channel layer, so you don't need to install PostgreSQL or Redis.

Option 2: Run with Docker (PostgreSQL + Redis)
bash
cp .env.example .env
docker compose up --build

Open http://localhost:8000.

⚙️ Environment variables
Variable	Purpose	Default
DJANGO_SECRET_KEY	Django secret key	dev-only key
DJANGO_DEBUG	Debug mode	true
DJANGO_ALLOWED_HOSTS	Comma-separated hostnames	localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS	Comma-separated origins (with scheme)	empty
DJANGO_SECURE_COOKIES	HTTPS-only cookies	true when DEBUG=false
POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT	Database connection; SQLite is used when POSTGRES_DB is unset	unset
REDIS_URL	Redis channel layer; in-memory is used when unset	unset
🧪 Running tests
bash
python manage.py test

27 tests cover moderation, rate limiting, views, the history API and the WebSocket consumer (auth, broadcast, typing, presence, DM privacy, origin check). GitHub Actions runs them against PostgreSQL on every push.

🔌 WebSocket protocol

Endpoint: ws(s)://<host>/ws/chat/<room-slug>/

Direction	type	Fields
Client → Server	message	content
Client → Server	typing	is_typing
Client → Server	read	—
Server → Client	message	id, room, author, content, flagged, created_at
Server → Client	typing	user, is_typing
Server → Client	presence	online (list of usernames)
Server → Client	error	message

Close codes: 4401 not logged in · 4403 no access (someone else's DM) · 4404 room not found

REST endpoint: GET /api/rooms/<slug>/messages/?before=<message-id> returns older messages, 50 per page.

📁 Project structure
pulsechat/
├── .github/workflows/ci.yml   # GitHub Actions: tests on every push
├── accounts/                  # sign-up view
├── chat/
│   ├── consumers.py           # ChatConsumer: WebSocket logic
│   ├── moderation.py          # word filter + rate limiter
│   ├── models.py              # Room, Membership, Message, Connection
│   ├── routing.py             # WebSocket URLs
│   ├── views.py               # pages, DMs, history API
│   ├── migrations/            # schema + seed rooms
│   └── tests/                 # unit + WebSocket tests
├── config/
│   ├── asgi.py                # HTTP + WebSocket routing
│   └── settings.py            # env-driven settings
├── static/                    # app.css, chat.js, ui.js
├── templates/                 # base, auth pages, chat page
├── docs/screenshots/          # README images
├── Dockerfile
├── docker-compose.yml         # web + PostgreSQL + Redis
└── requirements.txt
☁️ Deployment

Any host that runs Docker and supports WebSockets works: Render, Railway, Fly.io, or a VPS behind Nginx.

Create a PostgreSQL database and a Redis instance.
Set DJANGO_SECRET_KEY, DJANGO_DEBUG=false, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, the POSTGRES_* variables and REDIS_URL.
Deploy using the Dockerfile. It collects static files at build time and runs migrations on start.
Serve over HTTPS so the browser uses wss:// and cookies stay secure.
🗺️ Roadmap
 AI-based moderation behind the existing moderate() hook
 Edit and delete messages, emoji reactions
 Image and file sharing (S3)
 Read receipts and browser push notifications
 React / Next.js frontend on the same WebSocket API
 Presence stored in Redis with a TTL
