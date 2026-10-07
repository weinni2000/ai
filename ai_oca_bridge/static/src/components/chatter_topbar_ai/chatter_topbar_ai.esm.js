import {Component, t, useProps} from "@odoo/owl";
import {Chatter} from "@mail/chatter/web_portal_project/chatter";
import {ChatterAIItem} from "../chatter_topbar_ai_item/chatter_topbar_ai_item.esm";
import {Dropdown} from "@web/core/dropdown/dropdown";
import {DropdownItem} from "@web/core/dropdown/dropdown_item";

export class ChatterAITopbar extends Component {
    static template = "ai_oca_bridge.ChatterAITopbar";
    static components = {Dropdown, DropdownItem, ChatterAIItem};
    props = useProps({record: t.instanceOf(Chatter)});

    /**
     * @returns {Chatter}
     */
    get chatterTopbar() {
        return this.props.record;
    }
}

Object.assign(Chatter.components, {ChatterAITopbar});
