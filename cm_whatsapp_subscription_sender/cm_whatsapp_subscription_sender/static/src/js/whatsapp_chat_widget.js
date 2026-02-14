/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * WhatsApp Chat Widget - Embedded in subscription form
 * Shows a beautiful chat panel for the customer of the current subscription
 */
export class WhatsAppChatWidget extends Component {
    static template = "whatsapp_subscription_sender.WhatsAppChatWidget";
    static props = {
        ...standardFieldProps,
        record: { type: Object },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.messagesContainer = useRef("messagesContainer");

        this.state = useState({
            messages: [],
            newMessage: "",
            loading: true,
            partnerId: null,
            partnerName: "",
            partnerPhone: "",
            isExpanded: true,
        });

        onMounted(() => {
            this.loadMessages();
        });
    }

    get partnerId() {
        return this.props.record?.data?.partner_id?.[0] || null;
    }

    get partnerName() {
        return this.props.record?.data?.partner_id?.[1] || "Customer";
    }

    async loadMessages() {
        if (!this.partnerId) {
            this.state.loading = false;
            return;
        }

        this.state.loading = true;
        this.state.partnerId = this.partnerId;
        this.state.partnerName = this.partnerName;

        try {
            // Get partner phone
            const partner = await this.orm.read("res.partner", [this.partnerId], ["mobile", "phone"]);
            if (partner.length) {
                this.state.partnerPhone = partner[0].mobile || partner[0].phone || "";
            }

            // Get messages for this partner
            const messages = await this.orm.searchRead(
                "whatsapp.message.log",
                [["partner_id", "=", this.partnerId]],
                ["message", "direction", "status", "create_date", "failure_reason"],
                { order: "create_date asc", limit: 50 }
            );
            this.state.messages = messages;
        } catch (e) {
            console.error("Failed to load messages", e);
        }

        this.state.loading = false;
        this.scrollToBottom();
    }

    scrollToBottom() {
        setTimeout(() => {
            const container = this.messagesContainer.el;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 100);
    }

    // Safe notification helper
    notify(message, type = "info") {
        if (this.notification && this.notification.add) {
            try {
                this.notification.add(message, { type });
            } catch (e) {
                console.log("Notification:", message);
            }
        }
    }

    toggleExpanded() {
        this.state.isExpanded = !this.state.isExpanded;
    }

    async onSendMessage() {
        if (!this.state.newMessage.trim() || !this.partnerId) return;

        const messageText = this.state.newMessage.trim();
        this.state.newMessage = "";

        try {
            const result = await this.orm.call(
                "whatsapp.conversation",
                "send_chat_message",
                [this.partnerId, messageText]
            );

            if (result.status === "success") {
                this.notify("Message sent!", "success");
            } else {
                this.notify(`Error: ${result.message}`, "warning");
            }

            await this.loadMessages();
        } catch (e) {
            this.notify(`Failed to send: ${e.message}`, "danger");
        }
    }

    async onSendTemplate() {
        if (!this.partnerId) return;

        // Open template selector wizard
        const action = {
            type: "ir.actions.act_window",
            name: "Send WhatsApp Template",
            res_model: "whatsapp.subscription.sender",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_partner_id: this.partnerId,
                default_phone: this.state.partnerPhone,
            },
        };

        await this.env.services.action.doAction(action, {
            onClose: () => this.loadMessages(),
        });
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.onSendMessage();
        }
    }

    formatTime(dateStr) {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        if (date.toDateString() === today.toDateString()) {
            return "Today";
        } else if (date.toDateString() === yesterday.toDateString()) {
            return "Yesterday";
        }
        return date.toLocaleDateString();
    }

    getStatusIcon(status) {
        const icons = {
            pending: "⏳",
            sent: "✓",
            delivered: "✓✓",
            read: "✓✓",
            failed: "⚠",
            received: "📥",
        };
        return icons[status] || "•";
    }

    getStatusColor(status) {
        return status === "read" ? "#53bdeb" : status === "failed" ? "#ff6b6b" : "#8696a0";
    }
}

// Register as a field widget
registry.category("fields").add("whatsapp_chat_widget", {
    component: WhatsAppChatWidget,
});
