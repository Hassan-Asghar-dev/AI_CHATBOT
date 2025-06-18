import os
import re
import traceback
from typing import List, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import Groq
from fastapi.middleware.cors import CORSMiddleware
from transformers import pipeline
import requests
import random
import urllib.parse
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global constants
FALLBACK_GIF = "https://media.tenor.com/4zFMa2onE44AAAAC/funny-cat.gif"
FALLBACK_MESSAGE = "Couldn’t fetch a GIF due to network issues. Here’s a funny cat instead!"

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("API key for Groq is missing. Please set the GROQ_API_KEY in the .env file.")
if not TENOR_API_KEY:
    raise ValueError("API key for Tenor is missing. Please set the TENOR_API_KEY in the .env file.")
if TENOR_API_KEY.startswith("AIza"):
    logger.warning("TENOR_API_KEY appears to be a Google API key. Please use a valid Tenor API key from https://developers.google.com/tenor/guides/quickstart")

# Initialize FastAPI app
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)

# Load sentiment analysis model
sentiment_analyzer = pipeline("sentiment-analysis")

# Tone prompts
TONE_PROMPTS = {
    "serious": "You are a serious and professional assistant. 📘",
    "funny": "You are a funny and witty assistant 😂✨",
    "poetic": "You are a poetic AI who speaks in rhymes 🌸🎵",
    "dark_humor": "You are a dark-humored assistant 🖤💀🦃"
}

# Pydantic models
class UserInput(BaseModel):
    message: str
    role: str = "user"
    conversation_id: str

class NewChatRequest(BaseModel):
    conversation_id: str
    tone: str = "funny"
    title: str = "New Chat"

class RenameChatRequest(BaseModel):
    conversation_id: str
    new_title: str

# Conversation memory
class Conversation:
    def __init__(self, tone: str = "funny", title: str = "New Chat"):
        self.messages: List[Dict[str, str]] = []
        self.active: bool = True
        self.tone_set: bool = False
        self.current_tone: str = ""
        self.memory: Dict[str, str] = {}
        self.title: str = title
        self.set_tone(tone)

    def set_tone(self, tone: str):
        tone_key = tone.lower().strip()
        prompt = TONE_PROMPTS.get(tone_key)
        if not prompt:
            raise ValueError("Invalid tone. Options: funny, serious, poetic, dark_humor")
        self.messages = [{"role": "system", "content": prompt}]
        self.current_tone = tone_key
        self.tone_set = True

    def remember(self, message: str):
        name_match = re.search(r"\bmy name is (\w+)", message, re.IGNORECASE)
        mood_match = re.search(r"\bI(?:'m| am) (?:feeling|a bit)?\s*(\w+)", message, re.IGNORECASE)
        if name_match:
            self.memory["name"] = name_match.group(1).capitalize()
        if mood_match:
            mood = mood_match.group(1).lower()
            if mood not in ["a", "bit", "feeling"]:
                self.memory["mood"] = mood

    def inject_memory_context(self):
        mem = self.memory
        memory_facts = []
        if "name" in mem:
            memory_facts.append(f"The user's name is {mem['name']}.")
        if "mood" in mem:
            memory_facts.append(f"The user mentioned they were feeling {mem['mood']} earlier.")
        if memory_facts:
            context = " ".join(memory_facts)
            self.messages.insert(1, {"role": "system", "content": context})

# Store conversations
conversations: Dict[str, Conversation] = {}

def get_or_create_conversation(conversation_id: str) -> Conversation:
    if conversation_id not in conversations:
        conversations[conversation_id] = Conversation()
    return conversations[conversation_id]

def query_groq_api(conversation: Conversation) -> str:
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=conversation.messages,
            temperature=1,
            max_tokens=1024,
            top_p=1,
            stream=False
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Groq API failed: {str(e)}")

def get_gif_url(query: str) -> str:
    try:
        # Correct common misspellings
        query = query.lower().strip()
        if query == "peple":
            query = "people"
        # Encode query for URL
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.tenor.com/v2/search?key={TENOR_API_KEY}&q={encoded_query}&limit=5&contentfilter=medium"
        logger.info(f"Fetching GIF for query: {query}, URL: {url}")

        # Set up retry mechanism
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        
        response = session.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Tenor API response: {data}")
        gifs = data.get("results", [])
        if not gifs:
            logger.warning(f"No GIFs found for query: {query}")
            # Try fallback query
            url = f"https://api.tenor.com/v2/search?key={TENOR_API_KEY}&q=funny&limit=5&contentfilter=medium"
            logger.info(f"Trying fallback query: funny, URL: {url}")
            response = session.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            gifs = data.get("results", [])
        if gifs:
            gif_url = random.choice(gifs)["media_formats"]["gif"]["url"]
            logger.info(f"Selected GIF URL: {gif_url}")
            return gif_url
        logger.warning("No GIFs found even with fallback query")
        return FALLBACK_GIF
    except requests.exceptions.HTTPError as e:
        logger.error(f"Tenor API HTTP error: {str(e)}, Status: {e.response.status_code}")
        if e.response.status_code == 401:
            logger.error("Invalid Tenor API key or unauthorized access. Please check TENOR_API_KEY in .env")
        return FALLBACK_GIF
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Tenor API connection error: {str(e)}")
        logger.error("Check DNS settings or network connectivity. Unable to resolve api.tenor.com. On Windows, set DNS to 8.8.8.8 via Network Settings")
        return FALLBACK_GIF
    except requests.exceptions.RequestException as e:
        logger.error(f"Tenor API request failed: {str(e)}")
        return FALLBACK_GIF
    except Exception as e:
        logger.error(f"Unexpected error fetching GIF: {str(e)}")
        return FALLBACK_GIF

# GIF endpoint
@app.get("/gifs/{topic}")
async def get_gif(topic: str):
    topic = urllib.parse.unquote(topic)
    gif_url = get_gif_url(topic)
    if gif_url == FALLBACK_GIF:
        return {"topic": topic, "gif_url": gif_url, "message": FALLBACK_MESSAGE}
    if not gif_url:
        raise HTTPException(status_code=404, detail=f"No GIF found for '{topic}'. Try another topic!")
    return {"topic": topic, "gif_url": gif_url}

# Chat endpoint
@app.post("/chat/")
async def chat(input: UserInput):
    conversation = get_or_create_conversation(input.conversation_id)

    if not conversation.active:
        raise HTTPException(status_code=400, detail="Chat session ended.")

    user_msg = input.message.strip()

    # Handle GIF command
    if user_msg.lower().startswith("/gif"):
        topic = user_msg[5:].strip()
        if not topic:
            return {"response": "Please specify a topic after /gif", "conversation_id": input.conversation_id}
        gif_url = get_gif_url(topic)
        if gif_url == FALLBACK_GIF:
            response = f"{FALLBACK_MESSAGE}\n![GIF]({gif_url})"
        else:
            response = f"Here's a GIF for you!\n![GIF]({gif_url})" if gif_url else "Sorry, couldn't find a suitable GIF for that topic. Try another topic!"
        conversation.messages.append({"role": "user", "content": f"/gif {topic}"})
        conversation.messages.append({"role": "assistant", "content": response})
        return {"response": response, "conversation_id": input.conversation_id, "gif": gif_url if gif_url else None}

    # Handle tone change command
    if user_msg.lower().startswith("/tone"):
        tone = user_msg[5:].strip()
        if not tone:
            return {"response": "Please specify a tone after /tone", "conversation_id": input.conversation_id}
        try:
            conversation.set_tone(tone)
            gif_url = get_gif_url("celebrate") if tone == "funny" else ""
            if gif_url == FALLBACK_GIF:
                response = f"Tone changed to '{tone}'\n{FALLBACK_MESSAGE}\n![GIF]({gif_url})"
            else:
                response = f"Tone changed to '{tone}'" + (f"\n![GIF]({gif_url})" if gif_url else "")
            conversation.messages.append({"role": "assistant", "content": response})
            return {"response": response, "conversation_id": input.conversation_id, "gif": gif_url if gif_url else None}
        except ValueError:
            return {"response": "Invalid tone. Options: funny, serious, poetic, dark_humor.", "conversation_id": input.conversation_id}

    if not conversation.tone_set:
        return {
            "response": "👋 Hi! Choose your tone: `/tone funny`, `/tone serious`, `/tone poetic`, `/tone dark_humor`\nRequest a GIF with: `/gif <topic>`",
            "conversation_id": input.conversation_id
        }

    conversation.remember(user_msg)

    # Sentiment analysis
    sentiment_result = sentiment_analyzer(user_msg)[0]
    sentiment = sentiment_result['label'].lower()

    if sentiment == "positive":
        mood_note = "The user seems happy. Be playful and joyful in your response. 😄"
    elif sentiment == "negative":
        mood_note = "The user seems sad. Be empathetic and comforting in your response. 🥺"
    else:
        mood_note = "The user is neutral. Respond normally."

    if conversation.memory and not any("user's name" in m['content'] for m in conversation.messages):
        conversation.inject_memory_context()

    conversation.messages.append({"role": "system", "content": mood_note})
    conversation.messages.append({"role": input.role, "content": input.message})

    response = query_groq_api(conversation)
    
    # Add GIF for positive sentiment or funny tone, but not always (30% chance)
    gif_url = None
    if (sentiment == "positive" or conversation.current_tone == "funny") and random.random() < 0.3:
        gif_query = "happy" if sentiment == "positive" else "funny"
        gif_url = get_gif_url(gif_query)
        if gif_url == FALLBACK_GIF:
            response += f"\n{FALLBACK_MESSAGE}\n![GIF]({gif_url})"
        elif gif_url:
            response += f"\n![GIF]({gif_url})"

    conversation.messages.append({"role": "assistant", "content": response})

    return {"response": response, "conversation_id": input.conversation_id, "gif": gif_url if gif_url else None}

# New chat
@app.post("/chat/new/")
async def new_chat(data: NewChatRequest):
    if data.conversation_id in conversations:
        raise HTTPException(status_code=400, detail="Chat ID already exists.")
    conversations[data.conversation_id] = Conversation(tone=data.tone, title=data.title)
    return {"message": f"Chat '{data.title}' created.", "conversation_id": data.conversation_id}

# List chats
@app.get("/chat/list/")
async def list_chats():
    return [{"conversation_id": cid, "title": conv.title, "tone": conv.current_tone} for cid, conv in conversations.items()]

# Delete chat
@app.delete("/chat/delete/{conversation_id}")
async def delete_chat(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Chat not found.")
    del conversations[conversation_id]
    return {"message": f"Chat '{conversation_id}' deleted."}

# Rename chat
@app.put("/chat/rename/")
async def rename_chat(data: RenameChatRequest):
    chat = conversations.get(data.conversation_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    chat.title = data.new_title
    return {"message": f"Chat renamed to '{data.new_title}'."}

# Get chat history
@app.get("/chat/history/")
async def get_chat_history(conversation_id: str):
    conversation = conversations.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Chat not found.")

    history = [
        {"sender": msg["role"], "text": msg["content"]}
        for msg in conversation.messages
        if msg["role"] in ["user", "assistant"]
    ]
    return history

# Run app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)