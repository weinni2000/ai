import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {ListController} from "@web/views/list/list_controller";
import {listView} from "@web/views/list/list_view";
import {onMounted, onWillStart, proxy} from "@odoo/owl";

export class AiConnectionListController extends ListController {
    static template = "ai_open_IAP_module.ListController";

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.connectionSidebar = proxy({
            connections: [],
            selectedConnectionId: false,
            endpoint: "",
            webhookUrl: "",
            loading: true,
            credits: {loading: true, hasAccount: false, credit: 0, buyUrl: false},
        });
        onWillStart(() => this.loadOpenIapConnections());
        // Not awaited: the balance comes from Odoo's IAP servers and may be slow.
        onMounted(() => this.loadOpenIapCredits());
    }

    async loadOpenIapCredits() {
        const credits = this.connectionSidebar.credits;
        credits.loading = true;
        try {
            const result = await this.orm.silent.call(
                "ai.connection",
                "get_open_iap_credits",
                []
            );
            credits.hasAccount = result.has_account;
            credits.credit = result.credit;
            credits.buyUrl = result.buy_url;
        } catch {
            credits.hasAccount = true;
            credits.credit = -1;
        } finally {
            credits.loading = false;
        }
    }

    async loadOpenIapConnections() {
        this.connectionSidebar.loading = true;
        const result = await this.orm.call(
            "ai.connection",
            "get_open_iap_connection_selection",
            []
        );
        this.connectionSidebar.connections = result.connections;
        this.connectionSidebar.selectedConnectionId = result.selected_connection_id;
        this.connectionSidebar.endpoint = result.endpoint;
        this.connectionSidebar.webhookUrl = result.webhook_url;
        this.connectionSidebar.loading = false;
    }

    async selectOpenIapConnection(connectionId) {
        const result = await this.orm.call("ai.connection", "set_open_iap_connection", [
            connectionId,
        ]);
        this.connectionSidebar.connections = result.connections;
        this.connectionSidebar.selectedConnectionId = result.selected_connection_id;
        this.connectionSidebar.endpoint = result.endpoint;
        this.connectionSidebar.webhookUrl = result.webhook_url;
        const connection = result.connections.find((item) => item.id === connectionId);
        this.notification.add(
            connection
                ? `Odoo AI now uses ${connection.name} via the local proxy.`
                : "Odoo AI now uses the standard Odoo IAP.",
            {type: "success"}
        );
    }
}

export const aiConnectionListView = {
    ...listView,
    Controller: AiConnectionListController,
};

registry.category("views").add("ai_connection_list_with_sidebar", aiConnectionListView);
