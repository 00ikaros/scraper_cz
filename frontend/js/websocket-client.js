/**
 * WebSocket Client for Bloomberg Scraper
 */

class WebSocketClient {
    constructor(url, token) {
        this.url = url;
        this.token = token || null;
        this.ws = null;
        this.clientId = this.generateClientId();
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;

        // Event handlers
        this.onConnectionChange = null;
        this.onMessage = null;
        this.onError = null;
    }
    
    generateClientId() {
        return `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
    
    connect() {
        console.log('Connecting to WebSocket...');
        let url = `${this.url}?client_id=${this.clientId}`;
        if (this.token) url += `&token=${encodeURIComponent(this.token)}`;
        try {
            this.ws = new WebSocket(url);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                
                if (this.onConnectionChange) {
                    this.onConnectionChange(true);
                }
                
                // Send ping every 30 seconds to keep connection alive
                this.startHeartbeat();
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('Received message:', data);
                    
                    if (this.onMessage) {
                        this.onMessage(data);
                    }
                } catch (error) {
                    console.error('Error parsing message:', error);
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                
                if (this.onError) {
                    this.onError(error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket closed');
                this.isConnected = false;
                this.stopHeartbeat();
                
                if (this.onConnectionChange) {
                    this.onConnectionChange(false);
                }
                
                // Attempt reconnection
                this.attemptReconnect();
            };
            
        } catch (error) {
            console.error('Connection error:', error);
            this.attemptReconnect();
        }
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            
            setTimeout(() => {
                this.connect();
            }, this.reconnectDelay);
        } else {
            console.error('Max reconnection attempts reached');
            if (this.onError) {
                this.onError(new Error('Could not reconnect to server'));
            }
        }
    }
    
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.isConnected) {
                this.send({ type: 'ping' });
            }
        }, 30000); // 30 seconds
    }
    
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
    }
    
    send(data) {
        if (this.isConnected && this.ws) {
            this.ws.send(JSON.stringify(data));
            console.log('Sent message:', data);
        } else {
            console.error('Cannot send message: not connected');
        }
    }
    
    sendUserResponse(responseData) {
        this.send({
            type: 'user_response',
            data: responseData,
            timestamp: new Date().toISOString()
        });
    }
    
    disconnect() {
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
        }
    }
}