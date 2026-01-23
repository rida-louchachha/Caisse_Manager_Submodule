/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
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
            searchQuery: "",  // Search/filter query
            showNewChatModal: false,  // New chat modal visibility
            newChatPhone: "",  // Phone for new chat
            newChatName: "",  // Name for new contact
            searchResults: [],  // Contact search results
            showEmojiPicker: false,  // Emoji picker visibility
            showDeleteConfirm: false,  // Delete confirmation modal
            pendingDeleteConv: null,  // Conversation pending deletion
        });

        this.isDestroyed = false;  // Track if component is destroyed

        onWillStart(async () => {
            await this.loadConversations();
        });

        onMounted(() => {
            this.scrollToBottom();
            // Start auto-polling every 5 seconds for real-time updates
            this.startPolling();
        });

        onWillUnmount(() => {
            // Stop polling when component is destroyed
            this.isDestroyed = true;
            this.stopPolling();
        });
    }

    startPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        // Poll every 5 seconds for new messages
        this.pollInterval = setInterval(async () => {
            // Skip if component is destroyed
            if (this.isDestroyed) {
                this.stopPolling();
                return;
            }
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

    // Safe notification helper - checks if service exists
    notify(message, type = "info") {
        if (this.notification && this.notification.add && !this.isDestroyed) {
            try {
                this.notification.add(message, { type });
            } catch (e) {
                console.log("Notification:", message);
            }
        }
    }

    async loadConversations(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            // Load conversations directly from whatsapp.conversation model
            // This ensures new conversations (even without messages) appear
            const conversations = await this.orm.searchRead(
                "whatsapp.conversation",
                [],
                ["id", "partner_id", "phone", "last_message", "last_message_date", "unread_count"],
                { order: "last_message_date desc" }
            );

            // Transform to our format, using phone as unique key
            const phoneMap = new Map();

            for (const conv of conversations) {
                const phone = conv.phone || '';
                if (!phoneMap.has(phone)) {
                    phoneMap.set(phone, {
                        id: conv.id,  // Use actual conversation ID
                        conversation_id: conv.id,
                        partner_id: conv.partner_id,
                        phone: phone,
                        last_message: this.truncateMessage(conv.last_message || ''),
                        last_message_date: conv.last_message_date,
                        unread_count: conv.unread_count || 0
                    });
                }
            }

            // Also check message logs for any phone numbers without a conversation record
            const messages = await this.orm.searchRead(
                "whatsapp.message.log",
                [["conversation_id", "=", false]],  // Only orphan messages
                ["partner_id", "phone", "message", "create_date", "direction", "is_read"],
                { order: "create_date desc", limit: 100 }
            );

            for (const msg of messages) {
                if (!msg.phone) continue;
                const phone = msg.phone;

                if (!phoneMap.has(phone)) {
                    phoneMap.set(phone, {
                        id: phone,  // Use phone as fallback ID
                        partner_id: msg.partner_id,
                        phone: phone,
                        last_message: this.truncateMessage(msg.message),
                        last_message_date: msg.create_date,
                        unread_count: 0
                    });
                }

                // Count unread
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

    async deleteConversation(conv) {
        // Show confirmation modal instead of deleting immediately
        this.state.pendingDeleteConv = conv;
        this.state.showDeleteConfirm = true;
    }

    cancelDelete() {
        this.state.showDeleteConfirm = false;
        this.state.pendingDeleteConv = null;
    }

    async confirmDelete() {
        const conv = this.state.pendingDeleteConv;
        if (!conv) return;

        // Close the modal
        this.state.showDeleteConfirm = false;
        this.state.pendingDeleteConv = null;

        // Remove from UI immediately (archive behavior)
        const convIndex = this.state.conversations.findIndex(c => c.id === conv.id);
        if (convIndex > -1) {
            this.state.conversations.splice(convIndex, 1);
        }

        // If this was the selected conversation, select another
        if (this.state.selectedConversation && this.state.selectedConversation.id === conv.id) {
            this.state.selectedConversation = this.state.conversations[0] || null;
            if (this.state.selectedConversation) {
                await this.loadMessages(this.state.selectedConversation);
            } else {
                this.state.messages = [];
            }
        }

        // Archive the conversation (delete conversation record but KEEP messages)
        // Messages are NOT deleted - they stay linked by phone number
        // If user starts a new chat with same phone, old messages will appear
        try {
            const convId = conv.conversation_id || conv.id;
            if (typeof convId === 'number') {
                // Only delete the conversation record, not the messages
                await this.orm.unlink("whatsapp.conversation", [convId]);
            }
            this.notification.add("Conversation archived", { type: "success" });
        } catch (e) {
            console.error("Failed to archive conversation:", e);
            await this.loadConversations();
        }
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

    // ===== SEARCH & FILTER FUNCTIONALITY =====

    get filteredConversations() {
        const query = (this.state.searchQuery || "").toLowerCase().trim();
        if (!query) {
            return this.state.conversations;
        }
        return this.state.conversations.filter(conv => {
            const name = this.getPartnerName(conv).toLowerCase();
            const phone = (conv.phone || "").toLowerCase();
            const message = (conv.last_message || "").toLowerCase();
            return name.includes(query) || phone.includes(query) || message.includes(query);
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    // ===== EMOJI PICKER =====

    toggleEmojiPicker() {
        this.state.showEmojiPicker = !this.state.showEmojiPicker;
    }

    getCommonEmojis() {
        return [
            // Smileys
            "😀", "😃", "😄", "😁", "😅", "😂", "🤣", "😊", "😇", "🙂", "😉", "😍", "🥰", "😘", "😋", "😎",
            // Gestures
            "👍", "👎", "👌", "✌️", "🤞", "🤙", "👋", "🙏", "💪", "👏", "🤝", "❤️", "💯", "🔥", "⭐", "✨",
            // Objects
            "📱", "💻", "📧", "📞", "💰", "💵", "🏠", "🚗", "✈️", "🎉", "🎁", "📦", "📄", "✅", "❌", "⏰",
            // Arrows & symbols  
            "➡️", "⬅️", "⬆️", "⬇️", "↩️", "🔄", "ℹ️", "❓", "❗", "💡", "🔔", "📌", "🔗", "💬", "📝", "🗓️"
        ];
    }

    insertEmoji(emoji) {
        this.state.newMessage = (this.state.newMessage || "") + emoji;
        this.state.showEmojiPicker = false;
    }

    // ===== NEW CHAT MODAL =====

    openNewChatModal() {
        this.state.showNewChatModal = true;
        this.state.newChatPhone = "";
        this.state.newChatName = "";
        this.state.searchResults = [];
    }

    closeNewChatModal() {
        this.state.showNewChatModal = false;
    }

    onNewChatPhoneInput(ev) {
        this.state.newChatPhone = ev.target.value;
    }

    onNewChatNameInput(ev) {
        this.state.newChatName = ev.target.value;
    }

    async searchContacts() {
        const query = this.state.newChatPhone || this.state.newChatName;
        if (!query || query.length < 2) {
            this.state.searchResults = [];
            return;
        }
        try {
            // Search contacts by name, phone, or mobile
            this.state.searchResults = await this.orm.searchRead(
                "res.partner",
                [
                    "|", "|", "|",
                    ["name", "ilike", query],
                    ["phone", "ilike", query],
                    ["mobile", "ilike", query],
                    ["email", "ilike", query]
                ],
                ["id", "name", "phone", "mobile", "email"],
                { limit: 10 }
            );
        } catch (e) {
            console.error("Failed to search contacts:", e);
            this.state.searchResults = [];
        }
    }

    async startChatWithContact(contact) {
        // Get phone from contact
        const phone = contact.mobile || contact.phone;
        if (!phone) {
            this.notification.add("Contact has no phone number", { type: "warning" });
            return;
        }

        // Create or find conversation
        await this.startNewChat(phone, contact.name, contact.id);
    }

    async startNewChat(phone, name, partnerId = null) {
        if (!phone) {
            this.notification.add("Please enter a phone number", { type: "warning" });
            return;
        }

        // Clean phone number
        const cleanPhone = phone.replace(/[^\d+]/g, "");

        try {
            // Check if conversation already exists (in current list)
            let existingConv = this.state.conversations.find(c =>
                c.phone && c.phone.replace(/[^\d]/g, "").slice(-9) === cleanPhone.replace(/[^\d]/g, "").slice(-9)
            );

            if (existingConv) {
                // Select existing conversation
                await this.selectConversation(existingConv);
                this.closeNewChatModal();
                this.notification.add("Opened existing conversation", { type: "info" });
                return;
            }

            // Create new conversation via backend
            const result = await this.orm.call(
                "whatsapp.conversation",
                "get_or_create_conversation_by_phone",
                [cleanPhone, name, partnerId]
            );

            if (result && result.id) {
                // Reload conversations
                await this.loadConversations();

                // Find the new conversation by ID first, then by phone
                let newConv = this.state.conversations.find(c => c.id === result.id || c.conversation_id === result.id);
                if (!newConv) {
                    // Fallback to phone matching
                    const resultPhone = (result.phone || cleanPhone).replace(/[^\d]/g, "").slice(-9);
                    newConv = this.state.conversations.find(c =>
                        c.phone && c.phone.replace(/[^\d]/g, "").slice(-9) === resultPhone
                    );
                }

                if (newConv) {
                    this.state.selectedConversation = newConv;
                    await this.loadMessages(newConv);
                    this.scrollToBottom();
                    this.notification.add("Chat started!", { type: "success" });
                } else {
                    // Conversation created but not found in list - try selecting first one
                    if (this.state.conversations.length > 0) {
                        await this.selectConversation(this.state.conversations[0]);
                    }
                    this.notification.add("Chat created! Check your conversations.", { type: "success" });
                }
            }
        } catch (e) {
            console.error("Failed to start new chat:", e);
            this.notification.add("Failed to start chat: " + (e.message || e), { type: "danger" });
        }

        this.closeNewChatModal();
    }

    async createNewContact() {
        const phone = this.state.newChatPhone;
        const name = this.state.newChatName || `Contact ${phone}`;

        if (!phone) {
            this.notification.add("Please enter a phone number", { type: "warning" });
            return;
        }

        try {
            // Create new contact
            const partnerId = await this.orm.create("res.partner", [{
                name: name,
                mobile: phone,
            }]);

            // Start chat with this new contact
            await this.startNewChat(phone, name, partnerId);
            this.notification.add(`Contact "${name}" created!`, { type: "success" });
        } catch (e) {
            console.error("Failed to create contact:", e);
            this.notification.add("Failed to create contact: " + e.message, { type: "danger" });
        }
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

    formatFullDate(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        const options = {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        };
        return date.toLocaleDateString(undefined, options);
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
