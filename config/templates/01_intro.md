---
subject: "Food truck night for {{ property.name }} residents?"
---
Hi {{ contact.first_name or "there" }}!

I run Grilly Cheese, a grilled cheese food truck out of {{ business.home_town }}. We set up at apartment communities around {{ property.city or "the area" }} for resident dinner nights — we roll in, residents come down and order at the window, and you get an easy amenity night without planning a thing.
{% if property.hosts_food_trucks %}
I saw {{ property.name }} has had trucks out before, so you already know how these go.
{%- elif property.event_signal %}
I saw {{ property.name }} runs resident events{{ " for your " ~ property.unit_count ~ " homes" if property.unit_count }} — this slots right into that calendar.
{%- elif property.unit_count %}
With {{ property.unit_count }} homes on site, you have more than enough foot traffic to make a night work.
{%- endif %}

How it works: residents pay at the window, so there's no per-head catering bill. You cover a {{ offer.guarantee_display }} sales guarantee, and it's fully refundable — if we hit that in sales, you owe nothing. Most communities never pay a dime.

I have these {{ offer.service_window }} evenings open right now:
{% for d in offered_dates %}
  • {{ d }}
{%- endfor %}

Want me to hold one of those for {{ property.name }}?

{% include "_signature.md" %}
