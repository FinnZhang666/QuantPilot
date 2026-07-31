def format_related_objects(overview):
    labels = (("holding", "Holding"), ("trade_plan", "Trade Plan"),
              ("review", "Review"), ("ai", "AI"))
    return "\n".join("%s\n%s" % (
        label, "READY" if overview.related_objects[key]["available"] else "NONE",
    ) for key, label in labels)


def format_symbol_overview(overview):
    return "%s\nMarket\n%s\n%s" % (
        overview.symbol, overview.market, format_related_objects(overview),
    )
