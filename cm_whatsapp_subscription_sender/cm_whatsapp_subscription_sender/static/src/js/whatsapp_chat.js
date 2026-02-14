/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class WhatsAppChatView extends Component {
    static template = "whatsapp_subscription_sender.WhatsAppChatView";
    static props = {
        // Props Odoo standard pour les Client Actions
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        updateActionState: { type: Function, optional: true },  // ✅ AJOUTÉ
        className: { type: String, optional: true },            // ✅ AJOUTÉ
        // Props optionnels supplémentaires qu'Odoo peut passer
        "*": true,  // ✅ Accepter tous les autres props
    
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
            selectedPartner: {},
            selectedChannelInfo: {},
            partnerImageById: {},
            loading: true,
            newMessage: "",
            selectedChannel: "whatsapp",  // Default channel for sending
            searchQuery: "",  // Search/filter query
            showNewChatModal: false,  // New chat modal visibility
            newChatQuery: "",  // Search text (name/phone/email)
            searchResults: [],  // Contact search results
            selectedSearchContact: null, // Contact selected in popup
            searchPerformed: false, // Display "not found" helper text
            showEmojiPicker: false,  // Emoji picker visibility
            showDeleteConfirm: false,  // Delete confirmation modal
            pendingDeleteConv: null,  // Conversation pending deletion
            activeChannelFilter: "all", // all / whatsapp / instagram / messenger / facebook
            activeInboxFilter: "all", // all / unread
            isInternalComment: false, // write note without sending to client
            // Audio message
            isRecordingAudio: false,
            audioBlob: null,
            recordingStartTime: null,
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

    getConversationMapKey(record) {
        const phone = record.phone || "";
        if (phone) {
            return phone;
        }
        const partnerId = record.partner_id && Array.isArray(record.partner_id) ? record.partner_id[0] : null;
        const channelType = (record.channel_type || "instagram").toLowerCase();
        const externalUserId = record.external_user_id || "";
        if (externalUserId) {
            return `${channelType}_${externalUserId}`;
        }
        if (partnerId) {
            return `${channelType}_partner_${partnerId}`;
        }
        return `${channelType}_unknown`;
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
            ["id", "partner_id", "phone", "platform", "channel_id", "external_user_id",
 "last_message", "last_message_date", "unread_count"],
            { order: "last_message_date desc" }
        );

        // Transform to our format
        // For WhatsApp we use phone as key; for channels without phone we use partner_id as key
        const phoneMap = new Map();

        for (const conv of conversations) {
            const phone = conv.phone || "";
            const platform = conv.platform || "whatsapp";

            // 1) WhatsApp (key = phone)
            if (phone && !phoneMap.has(phone)) {
                phoneMap.set(phone, {
                    id: conv.id,
                    conversation_id: conv.id,
                    partner_id: conv.partner_id,
                    phone: phone,
                    channel_type: platform,          // platform -> channel_type
                    channel_id: conv.channel_id,
                    external_user_id: conv.external_user_id,
                    last_message: this.truncateMessage(conv.last_message || ""),
                    last_message_date: conv.last_message_date,
                    unread_count: conv.unread_count || 0,
                });
                continue;
            }

            // 2) Instagram/Messenger (no phone)
            if (!phone && ["instagram", "messenger", "facebook"].includes(platform) && conv.partner_id && Array.isArray(conv.partner_id)) {
                const key = this.getConversationMapKey({
                    phone: "",
                    partner_id: conv.partner_id,
                    channel_type: platform,
                    external_user_id: conv.external_user_id,
                });
                if (!phoneMap.has(key)) {
                    phoneMap.set(key, {
                        id: key,
                        conversation_id: conv.id,
                        partner_id: conv.partner_id,
                        phone: "",
                        channel_type: platform === "facebook" ? "messenger" : platform,
                        channel_id: conv.channel_id,
                        external_user_id: conv.external_user_id,
                        last_message: this.truncateMessage(conv.last_message || ""),
                        last_message_date: conv.last_message_date,
                        unread_count: conv.unread_count || 0,
                    });
                }
            }
        }


        // Also check message logs for any messages without a conversation record
        const messages = await this.orm.searchRead(
            "whatsapp.message.log",
            [["conversation_id", "=", false]],  // Only orphan messages
            [
                "partner_id",
                "phone",
                "message",
                "create_date",
                "direction",
                "is_read",
                "channel_type",
                "channel_icon",
                "channel_color",
                "conversation_id",
                "external_user_id", 
            ],
            { order: "create_date desc", limit: 100 }
        );

        for (const msg of messages) {
            // 1) If phone exists => WhatsApp-like message (key = phone)
            if (msg.phone) {
                const phone = msg.phone;

                if (!phoneMap.has(phone)) {
                    phoneMap.set(phone, {
                        id: phone,               // fallback ID
                        conversation_id: msg.conversation_id ? msg.conversation_id[0] : null,
                        partner_id: msg.partner_id,
                        phone: phone,
                        last_message: this.truncateMessage(msg.message || ""),
                        last_message_date: msg.create_date,
                        unread_count: 0,
                        channel_type: msg.channel_type || "whatsapp",
                        channel_icon: msg.channel_icon,
                        channel_color: msg.channel_color,
                    });
                }

                // Count unread
                if (msg.direction === "incoming" && !msg.is_read) {
                    const conv = phoneMap.get(phone);
                    conv.unread_count = (conv.unread_count || 0) + 1;
                }
                continue;
            }

            // 2) If no phone (Instagram/Messenger/etc.) => key by channel + external_user_id/partner
            if (msg.partner_id && Array.isArray(msg.partner_id)) {
                const channelType = (msg.channel_type || "instagram").toLowerCase();
                const key = this.getConversationMapKey({
                    phone: "",
                    partner_id: msg.partner_id,
                    channel_type: channelType,
                    external_user_id: msg.external_user_id,
                });

                if (!phoneMap.has(key)) {
                    phoneMap.set(key, {
                        id: key,                // stable key for UI list
                        conversation_id: msg.conversation_id ? msg.conversation_id[0] : null,
                        partner_id: msg.partner_id,
                        phone: "",              // no phone for Instagram
                        last_message: this.truncateMessage(msg.message || ""),
                        last_message_date: msg.create_date,
                        unread_count: 0,
                        channel_type: channelType,
                        channel_icon: msg.channel_icon,
                        channel_color: msg.channel_color,
                        external_user_id: msg.external_user_id,
                    });
                }

                // Count unread
                if (msg.direction === "incoming" && !msg.is_read) {
                    const conv = phoneMap.get(key);
                    conv.unread_count = (conv.unread_count || 0) + 1;
                }
            }
        }

        this.state.conversations = Array.from(phoneMap.values());

        // Preload partner images once for conversation list avatars
        const partnerIds = this.state.conversations
            .map((c) => (c.partner_id && Array.isArray(c.partner_id) ? c.partner_id[0] : null))
            .filter((id) => !!id);
        await this.preloadPartnerImages(partnerIds);
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
        if (conversation && conversation.channel_type) {
            this.state.selectedChannel = conversation.channel_type;
        }
        await this.loadSelectedPartner(conversation);
        await this.loadSelectedChannelInfo(conversation);
        await this.loadMessages(conversation);
        setTimeout(() => this.scrollToBottom(), 100);
    }

    async loadSelectedPartner(conversation) {
        this.state.selectedPartner = {};
        if (!conversation || !conversation.partner_id || !Array.isArray(conversation.partner_id)) {
            return;
        }
        const partnerId = conversation.partner_id[0];
        if (!partnerId) return;
        try {
            const rows = await this.orm.searchRead(
                "res.partner",
                [["id", "=", partnerId]],
                ["name", "phone", "mobile", "email"],
                { limit: 1 }
            );
            this.state.selectedPartner = (rows && rows.length && rows[0]) ? rows[0] : {};
        } catch (e) {
            console.error("Failed to load selected partner:", e);
            this.state.selectedPartner = {};
        }
    }

    async loadSelectedChannelInfo(conversation) {
        this.state.selectedChannelInfo = {};
        if (!conversation || !conversation.channel_id) {
            return;
        }
        const channelId = Array.isArray(conversation.channel_id) ? conversation.channel_id[0] : conversation.channel_id;
        if (!channelId) return;
        try {
            const rows = await this.orm.searchRead(
                "social.channel",
                [["id", "=", channelId]],
                ["name", "channel_type", "instagram_page_id", "facebook_page_id"],
                { limit: 1 }
            );
            this.state.selectedChannelInfo = (rows && rows.length && rows[0]) ? rows[0] : {};
        } catch (e) {
            console.error("Failed to load selected channel info:", e);
            this.state.selectedChannelInfo = {};
        }
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
            const phone = conversation.phone || "";

            // partner_id may be [id, name] or sometimes an id
            const partnerId = conversation.partner_id
                ? (Array.isArray(conversation.partner_id) ? conversation.partner_id[0] : conversation.partner_id)
                : null;

            let domain = [];

            if (phone) {
                // WhatsApp: load by phone (with/without +)
                domain = [
                    "|",
                    ["phone", "=", phone],
                    ["phone", "like", phone.replace("+", "")]
                ];
            } else if (partnerId) {
                const channelType = (conversation.channel_type || "").toLowerCase();
                if (channelType === "instagram" && conversation.external_user_id) {
                    domain = [
                        ["channel_type", "=", "instagram"],
                        ["external_user_id", "=", conversation.external_user_id],
                    ];
                } else if ((channelType === "messenger" || channelType === "facebook") && conversation.external_user_id) {
                    domain = [
                        ["channel_type", "in", ["messenger", "facebook"]],
                        ["external_user_id", "=", conversation.external_user_id],
                    ];
                } else if (channelType === "messenger" || channelType === "facebook") {
                    domain = [
                        ["channel_type", "in", ["messenger", "facebook"]],
                        ["partner_id", "=", partnerId],
                    ];
                } else {
                    // fallback: restrict to instagram for this partner
                    domain = [
                        ["channel_type", "=", "instagram"],
                        ["partner_id", "=", partnerId],
                    ];
                }
            } else {

                this.state.messages = [];
                return;
            }

            this.state.messages = await this.orm.searchRead(
                "whatsapp.message.log",
                domain,
                ["message", "direction", "status", "create_date", "phone", "partner_id", "channel_type", "channel_icon", "channel_color", "external_user_id", "media_type", "media_url", "media_attachment_id", "id"],
                { order: "create_date asc" }
            );

            // Ensure avatars in message list can use real partner photos
            const partnerIds = this.state.messages
                .map((m) => (m.partner_id && Array.isArray(m.partner_id) ? m.partner_id[0] : null))
                .filter((id) => !!id);
            await this.preloadPartnerImages(partnerIds);
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

    async preloadPartnerImages(partnerIds) {
        const uniq = [...new Set((partnerIds || []).filter((id) => !!id))];
        const missing = uniq.filter((id) => !(id in this.state.partnerImageById));
        if (!missing.length) return;
        try {
            const rows = await this.orm.searchRead(
                "res.partner",
                [["id", "in", missing]],
                ["id", "image_128"],
                { limit: missing.length }
            );
            const next = { ...this.state.partnerImageById };
            for (const id of missing) {
                next[id] = null;
            }
            for (const row of rows) {
                next[row.id] = row.image_128 || null;
            }
            this.state.partnerImageById = next;
        } catch (e) {
            console.error("Failed to preload partner images:", e);
        }
    }

    getPartnerImageUrl(partnerId) {
        if (!partnerId) return "";
        const imageData = this.state.partnerImageById[partnerId];
        if (!imageData) return "";
        return `data:image/png;base64,${imageData}`;
    }

    getConversationAvatarUrl(conversation) {
        if (!conversation || !conversation.partner_id || !Array.isArray(conversation.partner_id)) return "";
        return this.getPartnerImageUrl(conversation.partner_id[0]);
    }

    getMessageAvatarUrl(msg) {
        if (!msg || !msg.partner_id || !Array.isArray(msg.partner_id)) return "";
        return this.getPartnerImageUrl(msg.partner_id[0]);
    }

    getChannelIconUrl(channelType) {
        const c = (channelType || "whatsapp").toLowerCase();
        const base = "/cm_whatsapp_subscription_sender/static/src/img";
        const map = {
            whatsapp: "whatsapp.svg",
            instagram: "instagram.svg",
            messenger: "messenger.svg",
            facebook: "facebook.svg",
            tiktok: "tiktok.svg",
            telegram: "telegram.svg",
            email: "email.svg",
            sms: "sms.svg",
        };
        return `${base}/${map[c] || "whatsapp.svg"}`;
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
        return this.state.conversations.filter(conv => {
            const name = this.getPartnerName(conv).toLowerCase();
            const phone = (conv.phone || "").toLowerCase();
            const message = (conv.last_message || "").toLowerCase();
            const channel = (conv.channel_type || "whatsapp").toLowerCase();

            const matchesQuery = !query || name.includes(query) || phone.includes(query) || message.includes(query);
            const matchesChannel = this.state.activeChannelFilter === "all" || channel === this.state.activeChannelFilter;
            const matchesInbox = this.state.activeInboxFilter !== "unread" || (conv.unread_count || 0) > 0;
            return matchesQuery && matchesChannel && matchesInbox;
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    setActiveChannelFilter(filter) {
        this.state.activeChannelFilter = filter;
    }

    setActiveInboxFilter(filter) {
        this.state.activeInboxFilter = filter;
    }

    getChannelCount(channelType) {
        if (channelType === "all") {
            return this.state.conversations.length;
        }
        return this.state.conversations.filter(c => (c.channel_type || "whatsapp") === channelType).length;
    }

    getUnreadCount() {
        return this.state.conversations.reduce((acc, c) => acc + (c.unread_count || 0), 0);
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
        this.state.newChatQuery = "";
        this.state.searchResults = [];
        this.state.selectedSearchContact = null;
        this.state.searchPerformed = false;
    }

    closeNewChatModal() {
        this.state.showNewChatModal = false;
    }

    async onNewChatQueryInput(ev) {
        this.state.newChatQuery = ev.target.value || "";
        this.state.selectedSearchContact = null;
        await this.searchContacts(this.state.newChatQuery);
    }

    async searchContacts(queryValue = null) {
        const query = (queryValue !== null ? queryValue : this.state.newChatQuery || "").trim();
        if (!query || query.length < 2) {
            this.state.searchResults = [];
            this.state.searchPerformed = false;
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
            this.state.searchPerformed = true;
        } catch (e) {
            console.error("Failed to search contacts:", e);
            this.state.searchResults = [];
            this.state.searchPerformed = true;
        }
    }

    selectSearchContact(contact) {
        this.state.selectedSearchContact = contact || null;
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

    _extractPhone(rawText) {
        const value = (rawText || "").trim();
        const match = value.match(/(\+?\d[\d\s().-]{5,}\d)/);
        if (!match) return "";
        return match[1].replace(/[^\d+]/g, "");
    }

    _extractEmail(rawText) {
        const value = (rawText || "").trim();
        const match = value.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
        return match ? match[0] : "";
    }

    async submitNewChat() {
        const selected = this.state.selectedSearchContact;
        const query = (this.state.newChatQuery || "").trim();

        if (selected) {
            return this.startChatWithContact(selected);
        }

        if (!query) {
            this.notification.add("Sélectionnez ou saisissez un contact.", { type: "warning" });
            return;
        }

        const existing = this.state.searchResults && this.state.searchResults.length === 1
            ? this.state.searchResults[0]
            : null;
        if (existing) {
            return this.startChatWithContact(existing);
        }

        const phone = this._extractPhone(query);
        const email = this._extractEmail(query);
        const name = !phone && !email ? query : (query.replace(email, "").replace(phone, "").trim() || `Contact ${phone || email}`);

        if (!phone) {
            this.notification.add("Contact introuvable. Ajoute un numéro de téléphone pour démarrer le chat.", { type: "warning" });
            return;
        }

        try {
            const partnerId = await this.orm.create("res.partner", [{
                name: name || `Contact ${phone}`,
                mobile: phone,
                email: email || false,
            }]);
            await this.startNewChat(phone, name || `Contact ${phone}`, partnerId);
            this.notification.add("Contact n'existe pas: ajouté automatiquement.", { type: "success" });
        } catch (e) {
            console.error("Failed to create contact for new chat:", e);
            this.notification.add("Échec création contact: " + (e.message || e), { type: "danger" });
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

    getStatusLabel(status) {
        const labels = {
            read: "Read",
            delivered: "Delivered",
            sent: "Sent",
            received: "Received",
            failed: "Failed",
            pending: "Pending",
        };
        return labels[status] || "Sent";
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

    getComposerTitle() {
        const conv = this.state.selectedConversation || {};
        const channelType = (conv.channel_type || "").toLowerCase();
        if (channelType === "instagram") return "IG Messenger DM";
        if (channelType === "facebook" || channelType === "messenger") return "FB Messenger DM";
        if (channelType === "whatsapp") return "WhatsApp";
        return this.getChannelName(channelType || "whatsapp");
    }

    getComposerPageName() {
        const conv = this.state.selectedConversation || {};
        const channelType = (conv.channel_type || "").toLowerCase();
        const channelName = (this.state.selectedChannelInfo && this.state.selectedChannelInfo.name) || "";
        if (channelType === "instagram" || channelType === "facebook" || channelType === "messenger" || channelType === "tiktok") {
            return channelName || "-";
        }
        return "";
    }

    shouldShowComposerPage() {
        return !!this.getComposerPageName();
    }

    getComposerPlaceholder() {
        if (this.state.isInternalComment) {
            return "Write an internal note (not sent to client)";
        }
        return "Type a message";
    }

    toggleInternalCommentMode() {
        this.state.isInternalComment = !this.state.isInternalComment;
    }

    clearComposer() {
        this.state.newMessage = "";
        this.state.audioBlob = null;
        this.state.showEmojiPicker = false;
    }

    isInternalNote(msg) {
        const text = (msg && msg.message) || "";
        return typeof text === "string" && text.startsWith("[Internal]");
    }

    formatDisplayMessage(msg) {
        const text = (msg && msg.message) || "";
        if (this.isInternalNote(msg)) {
            return text.replace(/^\[Internal\]\s*/i, "");
        }
        return text;
    }

    onCallSelectedContact() {
        const phone = this.getSelectedPhone();
        if (!phone) {
            this.notification.add("Aucun numéro de téléphone sur ce contact.", { type: "warning" });
            return;
        }
        const ok = typeof window !== "undefined" ? window.confirm(`Call ${phone} ?`) : true;
        if (!ok) return;
        if (typeof window !== "undefined") {
            window.location.href = `tel:${phone}`;
        }
    }

    getSelectedPhone() {
        return this.state.selectedPartner.phone
            || this.state.selectedPartner.mobile
            || (this.state.selectedConversation ? this.state.selectedConversation.phone : "")
            || "";
    }

    async onOpenSelectedContactForm() {
        const conv = this.state.selectedConversation;
        const partnerId = conv && conv.partner_id && Array.isArray(conv.partner_id) ? conv.partner_id[0] : null;
        if (!partnerId) {
            this.notification.add("Aucun contact lié à cette conversation.", { type: "warning" });
            return;
        }
        try {
            await this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: partnerId,
                views: [[false, "form"]],
                target: "current",
            });
        } catch (e) {
            console.error("Failed to open contact form:", e);
            this.notification.add("Impossible d'ouvrir la fiche contact.", { type: "danger" });
        }
    }


    getAudioUrl(msg) {
        if (!msg) return null;
        if (msg.media_url) return msg.media_url;
        const attId = msg.media_attachment_id;
        const id = Array.isArray(attId) ? attId[0] : attId;
        if (id) {
            const base = typeof window !== "undefined" && window.location ? window.location.origin : "";
            return `${base}/web/content/${id}`;
        }
        return null;
    }

    async startAudioRecord() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const chunks = [];
            recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
            recorder.onstop = () => {
                stream.getTracks().forEach((t) => t.stop());
                const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
                this.state.audioBlob = blob;
            };
            this._audioRecorder = recorder;
            this._audioChunks = chunks;
            recorder.start(200);
            this.state.isRecordingAudio = true;
            this.state.recordingStartTime = Date.now();
        } catch (e) {
            console.error("Microphone access failed:", e);
            this.notification.add("Accès au micro refusé ou indisponible.", { type: "danger" });
        }
    }

    stopAudioRecord() {
        if (this._audioRecorder && this.state.isRecordingAudio) {
            this._audioRecorder.stop();
            this.state.isRecordingAudio = false;
            this.state.recordingStartTime = null;
        }
    }

    cancelAudioRecord() {
        this.stopAudioRecord();
        this.state.audioBlob = null;
        if (this._audioRecorder) this._audioRecorder = null;
    }

    async sendAudioMessage() {
        if (!this.state.audioBlob || !this.state.selectedConversation) return;
        const conversation = this.state.selectedConversation;
        const partnerId = conversation.partner_id ? (Array.isArray(conversation.partner_id) ? conversation.partner_id[0] : conversation.partner_id) : null;
        const phone = conversation.phone || "";
        const channelType = conversation.channel_type || this.state.selectedChannel || "whatsapp";
        const conversationId = conversation.conversation_id || null;
        const externalUserId = conversation.external_user_id || "";

        const blob = this.state.audioBlob;
        this.state.audioBlob = null;

        const toBase64 = (blob) =>
            new Promise((resolve, reject) => {
                const r = new FileReader();
                r.onload = () => {
                    const dataUrl = r.result;
                    const base64 = dataUrl.indexOf(",") >= 0 ? dataUrl.split(",")[1] : dataUrl;
                    resolve(base64);
                };
                r.onerror = reject;
                r.readAsDataURL(blob);
            });

        try {
            const ext = blob.type && blob.type.indexOf("ogg") >= 0 ? "ogg" : "webm";
            const filename = `audio_${Date.now()}.${ext}`;
            const datas = await toBase64(blob);
            const att = await this.orm.create("ir.attachment", {
                name: filename,
                datas: datas,
                res_model: "whatsapp.conversation",
                res_id: 0,
            });
            const attachmentId = att;

            const result = await this.orm.call(
                "whatsapp.conversation",
                "send_audio_message",
                [],
                {
                    partner_id: partnerId,
                    phone,
                    attachment_id: attachmentId,
                    conversation_id: conversationId,
                    channel_type: channelType,
                    external_user_id: externalUserId,
                }
            );

            if (result.status === "error") {
                this.notification.add(result.message || "Envoi audio échoué", { type: "danger" });
                return;
            }
            this.notification.add("Audio envoyé.", { type: "success" });
            await this.loadMessages(conversation);
            setTimeout(() => this.scrollToBottom(), 100);
        } catch (e) {
            console.error("Send audio failed:", e);
            this.notification.add("Envoi audio échoué: " + (e.message || e), { type: "danger" });
        }
    }

    async onSendMessage() {
        if (!this.state.newMessage.trim() || !this.state.selectedConversation) {
            return;
        }

        const conversation = this.state.selectedConversation;
        const messageText = this.state.newMessage.trim();

        const partnerId = conversation.partner_id
            ? (Array.isArray(conversation.partner_id) ? conversation.partner_id[0] : conversation.partner_id)
            : null;
        const channelId = conversation.channel_id
            ? (Array.isArray(conversation.channel_id) ? conversation.channel_id[0] : conversation.channel_id)
            : null;
        const phone = conversation.phone || "";
        const channelType = conversation.channel_type || this.state.selectedChannel || "whatsapp";

        this.state.newMessage = "";

        if (this.state.isInternalComment) {
            try {
                await this.orm.create("whatsapp.message.log", [{
                    partner_id: partnerId || false,
                    phone: phone || false,
                    message: `[Internal] ${messageText}`,
                    direction: "outgoing",
                    status: "sent",
                    is_read: true,
                    channel_id: channelId || false,
                    channel_type: channelType,
                    external_user_id: conversation.external_user_id || false,
                    conversation_id: conversation.conversation_id || false,
                }]);
                this.notification.add("Commentaire interne enregistré (non envoyé au client).", { type: "success" });
                await this.loadMessages(conversation);
                setTimeout(() => this.scrollToBottom(), 100);
            } catch (e) {
                console.error("Failed to save internal comment:", e);
                this.notification.add("Échec enregistrement commentaire interne: " + (e.message || e), { type: "danger" });
                this.state.newMessage = messageText;
            }
            return;
        }

        // Instagram: receiving + display OK, sending not wired yet
        // ✅ Instagram: log outgoing message via backend stub (no Meta yet)
        if (channelType === "instagram") {
            const externalUserId = conversation.external_user_id;

            if (!externalUserId) {
                this.notification.add(
                    "Impossible d'envoyer sur Instagram: external_user_id manquant (sender id).",
                    { type: "danger", sticky: true, title: "Message Not Sent" }
                );
                this.state.newMessage = messageText; // restore text
                return;
            }

            try {
                const result = await this.orm.call(
                    "social.channel",
                    "sendinstagrammessagereal",
                    [],
                    {
                        external_user_id: externalUserId,
                        message_text: messageText,
                        partner_id: partnerId,
                        channel_id: channelId,
                    }
                );

                // Le stub renvoie status='error' (car pas de Meta), mais il crée le log sortant
                this.notification.add(result.message || "Instagram: stub", {
                    type: "warning",
                    sticky: true,
                    title: "Instagram (Stub)",
                });

                await this.loadMessages(conversation);
                setTimeout(() => this.scrollToBottom(), 100);
                return;
            } catch (e) {
                console.error("Failed to send Instagram stub message:", e);
                this.notification.add("Failed to send Instagram message: " + (e.message || e), {
                    type: "danger",
                    sticky: true,
                    title: "Message Not Sent",
                });
                this.state.newMessage = messageText; // restore text
                return;
            }
        }


        if (channelType === "messenger" || channelType === "facebook") {
            const externalUserId = conversation.external_user_id;
            if (!externalUserId) {
                this.notification.add("Impossible d'envoyer sur Messenger: external_user_id manquant.", {
                    type: "danger",
                    sticky: true,
                    title: "Message Not Sent",
                });
                this.state.newMessage = messageText;
                return;
            }

            try {
                const result = await this.orm.call(
                    "social.channel",
                    "sendfacebookmessagereal",
                    [],
                    {
                        external_user_id: externalUserId,
                        message_text: messageText,
                        partner_id: partnerId,
                        channel_id: channelId,
                    }
                );

                if (result.status === "error") {
                    this.notification.add(result.message || "Messenger send failed", {
                        type: "danger",
                        sticky: true,
                        title: "Message Not Sent",
                    });
                } else {
                    this.notification.add("Message sent!", { type: "success" });
                }

                await this.loadMessages(conversation);
                setTimeout(() => this.scrollToBottom(), 100);
                return;
            } catch (e) {
                console.error("Failed to send Messenger message:", e);
                this.notification.add("Failed to send Messenger message: " + (e.message || e), {
                    type: "danger",
                    sticky: true,
                    title: "Message Not Sent",
                });
                this.state.newMessage = messageText;
                return;
            }
        }

        // WhatsApp: keep sending through existing model method
        try {
            const result = await this.orm.call(
                "whatsapp.conversation",
                "send_chat_message",
                [],
                {
                    partner_id: partnerId,
                    message_text: messageText,
                    phone: phone
                }
            );

            if (result.status === "error") {
                this.notification.add(result.message, {
                    type: "danger",
                    sticky: (result.message || "").includes("24-hour"),
                    title: "Message Not Sent",
                });
            } else {
                this.notification.add("Message sent!", { type: "success" });
            }

            await this.loadMessages(conversation);
            setTimeout(() => this.scrollToBottom(), 100);
        } catch (e) {
            console.error("Failed to send message:", e);
            this.notification.add("Failed to send message: " + (e.message || e), { type: "danger" });
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
