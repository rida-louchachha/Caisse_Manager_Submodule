/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onPatched } from "@odoo/owl";

/**
 * Patch ListRenderer to:
 * 1. Add Resume buttons and aggregates to group headers
 * 2. Sort data rows within groups by revenue (highest first)
 */
patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");

        onMounted(() => this._enhanceHierarchyView());
        onPatched(() => this._enhanceHierarchyView());
    },

    _isPartnerHierarchyView() {
        const model = this.props.list?.model?.config?.resModel ||
            this.props.list?.resModel || '';
        return model === 'res.partner';
    },

    /**
     * Main enhancement method - runs after render
     */
    _enhanceHierarchyView() {
        if (!this._isPartnerHierarchyView()) return;

        const tableRef = this.tableRef?.el;
        if (!tableRef) return;

        // Sort data rows within each group by revenue
        this._sortDataRowsByRevenue(tableRef);

        // Add aggregates and Resume buttons to group headers
        this._enhanceHierarchyGroupHeaders(tableRef);
    },

    /**
     * Sort data rows by revenue (highest first)
     * Handles both grouped and ungrouped views
     */
    _sortDataRowsByRevenue(tableRef) {
        const tbody = tableRef.querySelector('tbody');
        if (!tbody) return;

        const allRows = Array.from(tbody.querySelectorAll('tr'));
        if (!allRows.length) return;

        // Check if there are any group headers
        const hasGroups = allRows.some(row => row.classList.contains('o_group_header'));

        if (!hasGroups) {
            // No groups - sort all data rows together
            this._sortAllDataRows(tbody, allRows);
        } else {
            // Has groups - sort data rows within each group section
            let currentSectionStart = -1;
            let currentGroupLevel = -1;

            for (let i = 0; i < allRows.length; i++) {
                const row = allRows[i];

                if (row.classList.contains('o_group_header')) {
                    if (currentSectionStart >= 0) {
                        this._sortRowsInSection(tbody, allRows, currentSectionStart, i, currentGroupLevel);
                    }
                    currentSectionStart = i;
                    currentGroupLevel = this._getGroupLevel(row);
                }
            }

            // Sort the last section
            if (currentSectionStart >= 0) {
                this._sortRowsInSection(tbody, allRows, currentSectionStart, allRows.length, currentGroupLevel);
            }
        }
    },

    /**
     * Sort all data rows when there are no groups
     */
    _sortAllDataRows(tbody, allRows) {
        const dataRows = allRows.filter(row => row.classList.contains('o_data_row'));

        if (dataRows.length <= 1) return;

        // Calculate revenue for each data row
        const rowsWithRevenue = dataRows.map(row => ({
            row,
            revenue: this._getRowRevenue(row)
        }));

        // Sort by revenue descending
        rowsWithRevenue.sort((a, b) => b.revenue - a.revenue);

        // Reorder in DOM
        rowsWithRevenue.forEach(({ row }) => {
            tbody.appendChild(row);
        });
    },

    /**
     * Sort data rows within a specific section by revenue
     */
    _sortRowsInSection(tbody, allRows, startIdx, endIdx, parentLevel) {
        const headerRow = allRows[startIdx];
        const dataRows = [];
        const subGroups = [];

        // Collect data rows and sub-groups in this section
        for (let i = startIdx + 1; i < endIdx; i++) {
            const row = allRows[i];

            if (row.classList.contains('o_group_header')) {
                const level = this._getGroupLevel(row);
                if (level <= parentLevel) break; // End of this section
                subGroups.push({ row, level, index: i });
            } else if (row.classList.contains('o_data_row')) {
                dataRows.push(row);
            }
        }

        if (dataRows.length <= 1) return; // Nothing to sort

        // Calculate revenue for each data row
        const rowsWithRevenue = dataRows.map(row => ({
            row,
            revenue: this._getRowRevenue(row)
        }));

        // Sort by revenue descending
        rowsWithRevenue.sort((a, b) => b.revenue - a.revenue);

        // Reorder in DOM - insert after header (or after last sub-group header)
        let insertAfter = headerRow;

        // If there are sub-groups, we need to handle them differently
        // For now, just sort the data rows that appear directly after the header
        if (subGroups.length === 0) {
            rowsWithRevenue.forEach(({ row }) => {
                insertAfter.insertAdjacentElement('afterend', row);
                insertAfter = row;
            });
        }
    },

    /**
     * Get the revenue value from a data row
     */
    _getRowRevenue(row) {
        const revenueCell = row.querySelector('td[name="report_total_revenue"]');
        if (!revenueCell) return 0;
        return this._parseNumericValue(revenueCell.textContent);
    },

    _collectAllGroups(list, collected = []) {
        if (!list || !list.groups) return collected;
        for (const group of list.groups) {
            if (!group) continue;
            collected.push(group);
            if (group.list?.groups) {
                this._collectAllGroups(group.list, collected);
            }
        }
        return collected;
    },

    _getAllAggregateFields() {
        return [
            'report_total_revenue',
            'report_subscription_revenue',
            'report_total_invoiced',
            'report_total_paid',
            'report_amount_to_pay'
        ];
    },

    _enhanceHierarchyGroupHeaders(tableRef) {
        const allGroups = this._collectAllGroups(this.props.list);
        const allHeaderRows = Array.from(tableRef.querySelectorAll('tr.o_group_header'));

        const { visibleColumns, nonAggregateCount } = this._analyzeDataRowStructure(tableRef);

        if (!visibleColumns.length) return;

        allGroups.forEach((group) => {
            if (!group) return;

            const fieldName = group.groupByField?.name || '';
            if (fieldName !== 'hierarchy_client_id' && fieldName !== 'hierarchy_franchise_id') {
                return;
            }

            if (group.isFolded) return;

            const partnerId = group.serverValue;
            if (!partnerId) return;

            const displayName = group.displayName || '';
            const headerRow = this._findGroupHeaderRow(allHeaderRows, displayName);
            if (!headerRow) return;

            this._clearPreviousEnhancements(headerRow);

            const aggregates = this._calculateAggregatesFromDOM(headerRow, tableRef, visibleColumns);

            this._updateHeaderRowWithAggregates(headerRow, aggregates, visibleColumns, partnerId, nonAggregateCount);
        });
    },

    _analyzeDataRowStructure(tableRef) {
        const result = { visibleColumns: [], nonAggregateCount: 4 };

        const dataRow = tableRef.querySelector('tr.o_data_row');
        if (!dataRow) return result;

        const cells = dataRow.querySelectorAll('td');
        const aggregateFieldNames = this._getAllAggregateFields();

        let firstAggregateIndex = -1;

        cells.forEach((td, idx) => {
            const fieldName = td.getAttribute('name') || '';

            if (aggregateFieldNames.includes(fieldName)) {
                if (firstAggregateIndex === -1) {
                    firstAggregateIndex = idx;
                }
                result.visibleColumns.push({
                    index: idx,
                    name: fieldName,
                    type: 'monetary'
                });
            }
        });

        result.nonAggregateCount = firstAggregateIndex > 0 ? firstAggregateIndex : 4;

        return result;
    },

    _clearPreviousEnhancements(headerRow) {
        headerRow.querySelectorAll('.o_hierarchy_agg').forEach(el => el.remove());
        headerRow.querySelectorAll('.o_hierarchy_btn').forEach(el => el.remove());
    },

    _findGroupHeaderRow(allHeaderRows, displayName) {
        for (const header of allHeaderRows) {
            if (!header.classList.contains('o_group_open')) continue;

            const groupNameDiv = header.querySelector('.o_group_name .d-flex');
            if (!groupNameDiv) continue;

            if (groupNameDiv.textContent.trim().includes(displayName)) {
                return header;
            }
        }
        return null;
    },

    _calculateAggregatesFromDOM(headerRow, tableRef, visibleColumns) {
        const dataRows = this._getDataRowsForGroup(headerRow, tableRef);
        if (!dataRows.length) return {};

        const sums = {};
        visibleColumns.forEach(col => {
            sums[col.name] = { value: 0, type: col.type };
        });

        dataRows.forEach(row => {
            visibleColumns.forEach(col => {
                const cell = row.querySelector(`td[name="${col.name}"]`);

                if (cell) {
                    const text = cell.textContent.trim();
                    const value = this._parseNumericValue(text);
                    sums[col.name].value += value;
                }
            });
        });

        return sums;
    },

    _getDataRowsForGroup(headerRow, tableRef) {
        const dataRows = [];
        const allRows = Array.from(tableRef.querySelectorAll('tbody tr'));
        const headerIndex = allRows.indexOf(headerRow);

        if (headerIndex === -1) return dataRows;

        const thisLevel = this._getGroupLevel(headerRow);

        for (let i = headerIndex + 1; i < allRows.length; i++) {
            const row = allRows[i];

            if (row.classList.contains('o_group_header')) {
                const rowLevel = this._getGroupLevel(row);
                if (rowLevel <= thisLevel) break;
                continue;
            }

            if (row.classList.contains('o_data_row')) {
                dataRows.push(row);
            }
        }

        return dataRows;
    },

    _getGroupLevel(headerRow) {
        const caret = headerRow.querySelector('.o_group_caret');
        if (caret) {
            const style = caret.getAttribute('style') || '';
            const match = style.match(/--o-list-group-level:\s*(\d+)/);
            if (match) return parseInt(match[1], 10);
        }
        return 0;
    },

    _parseNumericValue(text) {
        if (!text) return 0;

        let cleaned = text.replace(/[A-Za-z]/g, '').trim();
        cleaned = cleaned.replace(/,/g, '').replace(/\s/g, '');

        const parsed = parseFloat(cleaned);
        return isNaN(parsed) ? 0 : parsed;
    },

    _updateHeaderRowWithAggregates(headerRow, aggregates, visibleColumns, partnerId, nonAggregateCount) {
        const groupNameCell = headerRow.querySelector('.o_group_name');
        if (!groupNameCell) return;

        headerRow.querySelectorAll('td:not(.o_hierarchy_agg):not(.o_hierarchy_btn)').forEach(td => td.remove());

        const existingLastTh = headerRow.querySelector('th:last-of-type');
        if (existingLastTh && existingLastTh !== groupNameCell) {
            existingLastTh.remove();
        }

        groupNameCell.setAttribute('colspan', nonAggregateCount.toString());

        let insertAfter = groupNameCell;

        visibleColumns.forEach(col => {
            const td = document.createElement('td');
            td.className = 'o_hierarchy_agg o_list_number text-end align-middle';
            td.style.cssText = 'padding: 0.25rem 0.5rem;';

            const agg = aggregates[col.name];
            if (agg && agg.value !== 0) {
                const formatted = this._formatValue(agg.value, col.type);
                td.innerHTML = `<strong>${formatted}</strong>`;
            } else {
                td.innerHTML = '';
            }

            insertAfter.insertAdjacentElement('afterend', td);
            insertAfter = td;
        });

        const buttonCell = document.createElement('td');
        buttonCell.className = 'o_hierarchy_btn text-end align-middle';
        buttonCell.style.cssText = 'padding: 2px 4px; width: 40px;';
        buttonCell.innerHTML = `
            <button class="o_hierarchy_resume_btn btn btn-sm btn-secondary px-2 py-1" 
                    data-partner-id="${partnerId}" title="View Resume"
                    style="font-size: 0.75rem;">
                <i class="fa fa-list-alt"></i>
            </button>
        `;

        buttonCell.querySelector('.o_hierarchy_resume_btn').addEventListener('click', (ev) => {
            ev.stopPropagation();
            this._openPartnerResume(partnerId);
        });

        insertAfter.insertAdjacentElement('afterend', buttonCell);
    },

    _formatValue(value, type) {
        if (type === 'monetary') {
            return value.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }) + ' DH';
        }
        return Math.round(value).toString();
    },

    _openPartnerResume(partnerId) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'Partner Resume',
            res_model: 'partner.resume.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: { default_partner_id: partnerId },
        });
    },
});
