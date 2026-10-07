import {Component, markup, t, useProps} from "@odoo/owl";
import {usePopover} from "@web/core/popover/popover_hook";

export class ChatterAIItemPopover extends Component {
    static template = "ai_oca_bridge.ChatterAIItemPopover";
    props = useProps({help: t.any().optional(), close: t.function().optional()});
}

export class ChatterAIItem extends Component {
    static template = "ai_oca_bridge.ChatterAIItem";
    props = useProps({bridge: t.object()});

    setup() {
        super.setup();
        this.popover = usePopover(ChatterAIItemPopover, {
            closeOnClickAway: true,
            position: "top",
        });
    }
    get tooltipInfo() {
        return {
            help: markup(this.props.bridge.description || ""),
        };
    }
    onMouseEnter(ev) {
        this.popover.open(ev.currentTarget, this.tooltipInfo);
    }

    onMouseLeave() {
        this.closeTooltip();
    }

    closeTooltip() {
        this.popover.close();
    }
}
