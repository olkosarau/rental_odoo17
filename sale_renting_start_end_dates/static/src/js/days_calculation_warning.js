/** @odoo-module **/

import { Dialog } from '@web/core/dialog/dialog';
import { FormController } from '@web/views/form/form_controller';
import { patch } from '@web/core/utils/patch';
import { _t } from '@web/core/l10n/translation';

console.log('days_calculation_warning.js loaded');

patch(FormController.prototype, {
    async _onFieldChanged(event) {
        if (event.data.changes.days_calculation_type) {
            const currentType = event.data.changes.days_calculation_type;
            const previousValue = this.model.root.data.days_calculation_type;

            if (currentType !== previousValue) {
                const confirmed = await new Promise((resolve) => {
                    const dialog = new Dialog(this, {
                        title: _t("Are you sure?"),
                        size: 'medium',
                        buttons: [
                            {
                                name: _t("Confirm"),
                                classes: "btn-primary",
                                click: function () {
                                    console.info("Position change confirmed");
                                    currentDialog.close();
                                    window.location.reload();
                                }
                            },
                            {
                                name: _t("Cancel"),
                                classes: "btn-secondary",
                                click: function () {
                                    console.info("Position change cancelled");
                                    currentDialog.close();
                                    window.location.reload();
                                }
                            }
                        ],
                    });
                    dialog.open();
                });

                if (!confirmed) {
                    this.model.root.data.days_calculation_type = previousValue;
                    return;
                }
            }
        }

        return this._super.apply(this, arguments);
    },
});

console.log('Patch applied');