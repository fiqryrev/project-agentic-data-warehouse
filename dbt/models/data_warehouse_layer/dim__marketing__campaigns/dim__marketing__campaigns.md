{% docs dim__marketing__campaigns %}

Marketing campaigns, one row per campaign, with its channel, the calendar month it runs and its
budget. The marketing source publishes three campaigns on the 1st of each month (and on
2026-01-01), each on a different channel. Analysts join it to `fact__marketing__daily_spend` to
compare what was spent against what was planned, and to name campaigns in reports.

## Potential Analyses

1. **Budget against actual spend** -- join `fact__marketing__daily_spend` on `campaign_id`, sum `spend_idr` per campaign and compare it with `budget_idr`.
2. **Channel mix per month** -- group by `date_trunc('month', start_date)` and `channel_name`, sum `budget_idr`, to see where each month's budget went.
3. **Campaign roster for a period** -- filter `start_date <= :day and end_date >= :day` to list the campaigns live on a given day.
4. **Cost per click by campaign** -- join the daily spend fact, then `sum(spend_idr) / nullif(sum(click_count), 0)` per `campaign_id` and `campaign_name`.

## Grain

One row per `campaign_id`.

## Table Lineage

```
dim__marketing__campaigns
└── staging__marketing__campaigns          (staging)
    └── lake.marketing__campaigns          (lake)
```

## Units and Conventions

- `budget_idr` is whole rupiah for the whole campaign.
- `campaign_id` is `<yyyymm> * 10 + n`, so it sorts by month and encodes it.
- `start_date` is the first and `end_date` the last day of the calendar month the campaign runs.
- `channel_name` is lower case: `google`, `meta`, `tiktok` or `email`.

## Known Caveats

- Each month uses three of the four channels (the channel rotates with the month), so one channel has no campaign that month; a missing channel is not a data gap.
- The budget is a plan, not a cap: daily spend is drawn around budget divided by days in the month, so a campaign's total spend can end above or below `budget_idr`.
- No generator defect touches campaigns (`generator/DEFECTS.md` lists none for marketing).

## Refresh Cadence

Rebuilt by the daily dbt build.

## Change History

| Version | Date | Author | Summary |
| --- | --- | --- | --- |
| 1.0.0 | 2026-11-22 | data-engineering | Initial doc block. |

{% enddocs %}
