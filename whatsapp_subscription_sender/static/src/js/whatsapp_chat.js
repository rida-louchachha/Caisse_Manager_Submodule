/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class WhatsAppChatView extends Component {
    static template = "whatsapp_subscription_sender.WhatsAppChatView";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.messagesRef = useRef("messagesContainer");
        this.pollInterval = null;

        this.state = useState({
            conversations: [],
            messages: [],
            selectedConversation: null,
            loading: true,
            newMessage: "",
            selectedChannel: "whatsapp",  // Default channel for sending
        });

        onWillStart(async () => {
            await this.loadConversations();
        });

        onMounted(() => {
            this.scrollToBottom();
            // Start auto-polling every 5 seconds for real-time updates
            this.startPolling();
        });
    }

    startPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        // Poll every 5 seconds for new messages
        this.pollInterval = setInterval(async () => {
            if (this.state.selectedConversation) {
                const currentMessageCount = this.state.messages.length;
                await this.loadMessages(this.state.selectedConversation);
                // Only scroll if new messages arrived
                if (this.state.messages.length > currentMessageCount) {
                    this.scrollToBottom();
                }
            }
            // Also refresh conversation list to update unread counts
            await this.loadConversations(true);  // silent refresh
        }, 5000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    scrollToBottom() {
        if (this.messagesRef.el) {
            this.messagesRef.el.scrollTop = this.messagesRef.el.scrollHeight;
        }
    }

    async loadConversations(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            // Build conversation list from message logs, keyed by PHONE NUMBER
            // This prevents mixing between different contacts with similar data
            const messages = await this.orm.searchRead(
                "whatsapp.message.log",
                [],
                ["partner_id", "phone", "message", "create_date", "direction", "status", "is_read"],
                { order: "create_date desc" }
            );

            // Key by PHONE NUMBER, not partner_id
            const phoneMap = new Map();

            for (const msg of messages) {
                if (!msg.phone) continue;

                const phone = msg.phone;

                // If we haven't seen this phone yet
                if (!phoneMap.has(phone)) {
                    phoneMap.set(phone, {
                        id: phone, // Use phone as the unique ID
                        partner_id: msg.partner_id,
                        phone: phone,
                        last_message: this.truncateMessage(msg.message),
                        last_message_date: msg.create_date,
                        unread_count: 0
                    });
                }

                // Calculate unread count (incoming and not read)
                if (msg.direction === 'incoming' && !msg.is_read) {
                    const conv = phoneMap.get(phone);
                    conv.unread_count = (conv.unread_count || 0) + 1;
                }
            }

            this.state.conversations = Array.from(phoneMap.values());

        } catch (e) {
            console.error("Failed to load conversations:", e);
            this.state.conversations = [];
        }
        this.state.loading = false;

        // Select first conversation if exists and none selected
        if (this.state.conversations.length > 0 && !this.state.selectedConversation) {
            await this.selectConversation(this.state.conversations[0]);
        }
    }

    async selectConversation(conversation) {
        this.state.selectedConversation = conversation;
        await this.loadMessages(conversation);
        setTimeout(() => this.scrollToBottom(), 100);
    }

    async loadMessages(conversation) {
        try {
            // Load messages by PHONE NUMBER for more accurate matching
            // This prevents messages from mixing between different conversations
            const phone = conversation.phone;

            // Build domain - match phone number (with or without + prefix)
            const domain = [
                "|",
                ["phone", "=", phone],
                ["phone", "like", phone.replace("+", "")]
            ];

            this.state.messages = await this.orm.searchRead(
                "whatsapp.message.log",
                domain,
                ["message", "direction", "status", "create_date", "phone", "partner_id", "channel_type", "channel_icon", "channel_color"],
                { order: "create_date asc" }
            );
        } catch (e) {
            console.error("Failed to load messages:", e);
            this.state.messages = [];
        }
    }

    getAvatarLetter(name) {
        if (!name) return "?";
        if (typeof name === 'string') {
            return name[0].toUpperCase();
        }
        return "?";
    }

    getPartnerName(conversation) {
        if (!conversation || !conversation.partner_id) return "Unknown";
        if (Array.isArray(conversation.partner_id)) {
            return conversation.partner_id[1] || "Unknown";
        }
        return conversation.partner_id;
    }

    formatTime(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    formatDate(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        const today = new Date();
        if (date.toDateString() === today.toDateString()) {
            return this.formatTime(dateString);
        }
        return date.toLocaleDateString();
    }

    isSelected(conversation) {
        return this.state.selectedConversation &&
            this.state.selectedConversation.id === conversation.id;
    }

    getStatusIcon(status) {
        switch (status) {
            case 'read': return '✓✓';
            case 'delivered': return '✓✓';
            case 'sent': return '✓';
            case 'received': return '';
            case 'failed': return '⚠';
            default: return '✓';
        }
    }

    getStatusColor(status) {
        switch (status) {
            case 'read': return '#53bdeb';
            case 'delivered': return '#8696a0';
            case 'sent': return '#8696a0';
            case 'failed': return '#ff6b6b';
            default: return '#8696a0';
        }
    }

    truncateMessage(message, maxLength = 50) {
        if (!message) return '';
        if (message.length <= maxLength) return message;
        return message.substring(0, maxLength) + '...';
    }

    // ========== CHANNEL HELPER METHODS ==========

    getChannelIcon(channelType) {
        const icons = {
            'whatsapp': '💬',
            'instagram': '📸',
            'facebook': '📘',
            'twitter': '𝕏',
            'linkedin': '💼',
            'youtube': '▶️',
            'sms': '📱',
            'email': '✉️',
            'telegram': '✈️',
            'messenger': '💬',
            'tiktok': '🎵',
        };
        return icons[channelType] || '💬';
    }

    getChannelColor(channelType) {
        const colors = {
            'whatsapp': '#25D366',
            'instagram': '#E4405F',
            'facebook': '#1877F2',
            'twitter': '#000000',
            'linkedin': '#0A66C2',
            'youtube': '#FF0000',
            'sms': '#4CAF50',
            'email': '#EA4335',
            'telegram': '#0088CC',
            'messenger': '#006AFF',
            'tiktok': '#000000',
        };
        return colors[channelType] || '#667eea';
    }

    getChannelName(channelType) {
        const names = {
            'whatsapp': 'WhatsApp',
            'instagram': 'Instagram',
            'facebook': 'Facebook',
            'twitter': 'X',
            'linkedin': 'LinkedIn',
            'youtube': 'YouTube',
            'sms': 'SMS',
            'email': 'Email',
            'telegram': 'Telegram',
            'messenger': 'Messenger',
            'tiktok': 'TikTok',
        };
        return names[channelType] || 'Unknown';
    }

    setSelectedChannel(channelType) {
        this.state.selectedChannel = channelType;
    }


    async onSendMessage() {
        if (!this.state.newMessage.trim() || !this.state.selectedConversation) {
            return;
        }

        const conversation = this.state.selectedConversation;
        const messageText = this.state.newMessage.trim();
        const partnerId = conversation.partner_id ? conversation.partner_id[0] : null;
        const phone = conversation.phone;

        this.state.newMessage = "";

        try {
            // Call the backend to send the message - pass phone for reliable matching
            const result = await this.orm.call(
                "whatsapp.conversation",
                "send_chat_message",
                [],
                {
                    partner_id: partnerId,
                    message_text: messageText,
                    phone: phone  // Pass phone for better conversation matching
                }
            );

            if (result.status === 'error') {
                this.notification.add(result.message, {
                    type: "danger",
                    sticky: result.message.includes("24-hour"),  // Make 24h errors sticky
                    title: "Message Not Sent"
                });
            } else {
                this.notification.add("Message sent!", { type: "success" });
            }

            // Reload messages regardless (to show the new message, even if failed)
            await this.loadMessages(conversation);

            // Scroll to bottom
            setTimeout(() => this.scrollToBottom(), 100);

        } catch (e) {
            console.error("Failed to send message:", e);
            this.notification.add("Failed to send message: " + e.message, { type: "danger" });
            // Restore message on error
            this.state.newMessage = messageText;
        }
    }

    async onOpenTemplateSelector() {
        // Open the WhatsApp template selector
        if (!this.state.selectedConversation) return;

        try {
            await this.actionService.doAction({
                type: 'ir.actions.act_window',
                name: 'Send WhatsApp Template',
                res_model: 'whatsapp.subscription.sender',
                view_mode: 'form',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    default_phone: this.state.selectedConversation.phone,
                    default_partner_id: this.state.selectedConversation.partner_id[0],
                },
            });
        } catch (e) {
            console.error("Failed to open template selector:", e);
        }
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.onSendMessage();
        }
    }

    async onRefresh() {
        if (this.state.selectedConversation) {
            await this.loadMessages(this.state.selectedConversation);
            this.notification.add("Messages refreshed", { type: "info" });
        } else {
            await this.loadConversations();
        }
    }
}

// Register as a client action
registry.category("actions").add("whatsapp_chat_client_action", WhatsAppChatView);
