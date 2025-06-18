import React, { useState, useEffect, useRef } from 'react';

// Chat message type
interface ChatMessage {
  sender: 'user' | 'ai';
  text: string;
}

interface ChatSession {
  conversation_id: string;
  title: string;
  tone: string;
}

const App: React.FC = () => {
  const [message, setMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChatSessions();
  }, []);

  useEffect(() => {
    if (!conversationId && chatSessions.length > 0) {
      setConversationId(chatSessions[0].conversation_id);
    }
  }, [chatSessions]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  const fetchChatSessions = async () => {
    const res = await fetch('http://localhost:8000/chat/list/');
    const data = await res.json();
    setChatSessions(data);
  };

  const createNewChat = async () => {
    const newId = Date.now().toString();
    await fetch('http://localhost:8000/chat/new/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: newId,
        tone: 'funny',
        title: `Chat ${chatSessions.length + 1}`,
      }),
    });
    await fetchChatSessions();
    setConversationId(newId);
    setChatHistory([]);
  };

  const loadChat = async (id: string) => {
  setConversationId(id);
  setChatHistory([]); // Clear current chat while loading

  try {
    const res = await fetch(`http://localhost:8000/chat/history/?conversation_id=${id}`);
    const data = await res.json();

    if (Array.isArray(data)) {
      setChatHistory(data);
    } else {
      console.error("Unexpected history format:", data);
    }
  } catch (error) {
    console.error("Failed to load chat history:", error);
    setChatHistory([{ sender: "ai", text: "⚠️ Failed to load this chat." }]);
  }
};


  const sendMessage = async () => {
    if (message.trim() === '' || !conversationId) return;

    setLoading(true);
    setChatHistory((prev) => [...prev, { sender: 'user', text: message }]);

    try {
      const res = await fetch('http://localhost:8000/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          role: 'user',
          conversation_id: conversationId,
        }),
      });

      const data = await res.json();
      setChatHistory((prev) => [...prev, { sender: 'ai', text: data.response }]);
      setMessage('');
    } catch (err) {
      console.error('Error:', err);
      setChatHistory((prev) => [...prev, { sender: 'ai', text: 'Server error.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.wrapper}>
      {/* Sidebar */}
      <div style={styles.sidebar}>
        <h2 style={styles.sidebarHeader}>💬 Chats</h2>
        <button onClick={createNewChat} style={styles.newChatButton}>
          + New Chat
        </button>
        {chatSessions.map((chat) => (
          <div
            key={chat.conversation_id}
            onClick={() => loadChat(chat.conversation_id)}
            style={{
              ...styles.chatItem,
              backgroundColor: chat.conversation_id === conversationId ? '#3b3b3b' : 'transparent',
            }}
          >
            {chat.title}
          </div>
        ))}
      </div>

      {/* Chat Area */}
      <div style={styles.container}>
        <h1 style={styles.header}>🤖 CHIP</h1>
        <div ref={chatContainerRef} style={styles.chatBox}>
          {chatHistory.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '10px',
              }}
            >
              <div
                style={{
                  backgroundColor: msg.sender === 'user' ? '#4f46e5' : '#444',
                  color: 'white',
                  padding: '10px 15px',
                  borderRadius: '10px',
                  maxWidth: '70%',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg.text}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ textAlign: 'left', color: 'gray', padding: '5px 0' }}>
              AI is typing...
            </div>
          )}
        </div>

        {/* Input section */}
        <div style={styles.inputSection}>
          <input
            type="text"
            placeholder="Type your message..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
              }
            }}
            style={styles.input}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !message.trim()}
            style={styles.button}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
};

// Styles
const styles = {
  wrapper: {
    display: 'flex',
    height: '100vh',
    background: 'linear-gradient(to right, #1e1e2f, #16161e)',
    color: '#f5f5f5',
    fontFamily: 'Segoe UI, Roboto, sans-serif',
    overflow: 'hidden',
  },
  sidebar: {
    width: '240px',
    backgroundColor: '#202030',
    padding: '20px',
    borderRight: '1px solid #333',
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
  },
  sidebarHeader: {
    fontSize: '1.4rem',
    fontWeight: 'bold',
    marginBottom: '20px',
    color: '#ffffffdd',
  },
  newChatButton: {
    marginBottom: '20px',
    backgroundColor: '#6a5acd',
    border: 'none',
    color: 'white',
    padding: '10px',
    borderRadius: '8px',
    cursor: 'pointer',
    fontWeight: '500',
    transition: 'all 0.2s ease-in-out',
  },
  chatItem: {
    padding: '10px',
    borderRadius: '6px',
    cursor: 'pointer',
    marginBottom: '8px',
    backgroundColor: '#29293d',
    color: '#ddd',
    transition: 'all 0.2s ease',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  container: {
    flex: 1,
    padding: '40px',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  header: {
    fontSize: '2.2rem',
    marginBottom: '30px',
    fontWeight: 'bold',
    color: '#ffffffee',
  },
  chatBox: {
    flex: 1,
    overflowY: 'auto' as const,
    background: 'rgba(255, 255, 255, 0.05)',
    padding: '20px',
    borderRadius: '16px',
    border: '1px solid #3a3a4a',
    backdropFilter: 'blur(10px)',
    marginBottom: '20px',
    boxShadow: '0 0 10px rgba(0,0,0,0.2)',
  },
  inputSection: {
    display: 'flex',
    gap: '12px',
    marginTop: 'auto',
  },
  input: {
    flex: 1,
    padding: '12px 18px',
    borderRadius: '12px',
    border: '1px solid #444',
    backgroundColor: '#2c2c3c',
    color: 'white',
    fontSize: '1rem',
    outline: 'none',
  },
  button: {
    padding: '12px 24px',
    backgroundColor: '#6a5acd',
    color: 'white',
    border: 'none',
    borderRadius: '12px',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
};


export default App;
