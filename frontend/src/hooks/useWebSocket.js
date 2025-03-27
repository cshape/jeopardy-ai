import { useEffect, useRef, useCallback } from 'react';

export default function useWebSocket(url, onMessage) {
  const ws = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('WebSocket message received:', message);
      
      // Simply pass the parsed message to the callback
      if (onMessage && typeof onMessage === 'function') {
        onMessage(message);
      }
    };

    ws.current.onopen = () => {
      console.log('WebSocket connection established');
      reconnectAttempts.current = 0;
    };

    ws.current.onclose = () => {
      if (reconnectAttempts.current < maxReconnectAttempts) {
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000);
        console.log(`WebSocket closed. Reconnecting in ${timeout}ms...`);
        reconnectAttempts.current += 1;
        setTimeout(connect, timeout);
      }
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }, [url, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((message, payload) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      // If message is an object with a topic property, use it as is
      // Otherwise, construct a message object from the message (topic) and payload parameters
      const messageToSend = typeof message === 'object' && message.topic 
        ? message  // Message is already in correct format with topic and payload
        : { topic: message, payload: payload };  // Create message from topic and payload
      
      console.log('Sending WebSocket message:', messageToSend);
      ws.current.send(JSON.stringify(messageToSend));
    } else {
      console.warn('WebSocket not connected, attempting to reconnect...');
      connect();
    }
  }, [connect]);

  return { sendMessage, ws: ws.current };
} 