---
subject: "What a resident food truck night actually looks like"
---
Hi {{ contact.first_name or "there" }},

Figured it might help to show what these nights look like rather than just describe them.

We pull in about 30 minutes before service, set up in a corner of the parking lot or by the clubhouse, and serve for {{ offer.service_window }}. Residents come down as they get home from work. You post it once in your resident app and we handle everything else — truck, staff, power, permits, insurance. We carry our own COI and can name {{ property.management_company or property.name }} as additional insured.
{% if property.portfolio_size > 1 %}
And if it works here, we're happy to set up a rotation across the rest of the {{ property.management_company or "portfolio" }} communities so you're not rebooking every time.
{%- endif %}

Menus and packages are here: {{ business.website }}

Still have {{ offered_dates | join(" and ") }} open.

{% include "_signature.md" %}
