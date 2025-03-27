import React, { useState, useEffect, useRef } from 'react';
import { useGame } from '../../contexts/GameContext';
import './ChatWindow.css';

export default function ChatWindow() {
  const { state, sendChatMessage } = useGame();
  const [message, setMessage] = useState('');
  const chatEndRef = useRef(null);

  // Scroll to bottom of chat when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.chatMessages]);

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (message.trim() === '') return;
    
    // Send the message using the context function
    sendChatMessage(message);
    
    // Clear the input
    setMessage('');
  };

  const formatTime = (date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <h3>Game Chat</h3>
      </div>
      <div className="chat-messages">
        {state.chatMessages.length === 0 ? (
          <div className="empty-chat-message">
            No messages yet. Be the first to chat!
          </div>
        ) : (
          state.chatMessages.map((msg, index) => (
            <div key={index} className="chat-message">
              <div className="message-header">
                <span className="message-user">{msg.user}</span>
                <span className="message-time">{formatTime(msg.timestamp)}</span>
              </div>
              <div className="message-text">{msg.text}</div>
            </div>
          ))
        )}
        <div ref={chatEndRef} />
      </div>
      <form onSubmit={handleSendMessage} className="chat-input">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type a message..."
        />
        <button type="submit">Send</button>
      </form>
    </div>
  );
} 