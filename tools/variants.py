"""Real shopping variants. Values are catalog endpoints, never product-page answers."""
import statistics

def catalogs(nonce, count, rich=False, both=True, price=False):
    fields = 'name,permalink'
    if price or rich:
        fields += ',prices'
    if rich:
        fields += ',short_description'
    args = f'per_page={count}&stock_status=instock&_fields={fields}&_run={nonce}'
    base = 'https://raspberrypi.dk/wp-json/wc/store/v1/products?search=kit&'
    if not both:
        return [base+args]
    return ['https://mercantile.wordpress.org/wp-json/wc/store/v1/products?'+args,base+args]

# Each arm describes a useful user-facing shopping result and a real choice between candidates.
VARIANTS = {
 'paired-links': (8,False,True,False,'Find five different Christmas gifts for people who enjoy making things. Use web_fetch on both in-stock retail catalogs in parallel. Include both shops. Return a numbered Markdown list with the exact product titles linked to their exact product pages.'),
 'hardware-links': (10,False,False,False,'Find five distinct real Christmas gifts suitable for hobby electronics from this live retailer. Fetch the catalog once with web_fetch and select five useful gifts for different projects. Return five numbered product titles as Markdown links to their actual product pages.'),
 'recipient-guide': (6,True,True,False,'Build a Christmas gift guide for a hybrid team of bloggers and hardware hobbyists. Use web_fetch in parallel on both live merchant stock lists. Choose five different items across the shops. For each give a Markdown link with the exact merchant title, its listed price in the original currency, and one concrete recipient or use case supported by the item. Keep the guide easy to scan.'),
 'kit-comparison': (8,True,False,False,'A family is shopping for five Christmas gifts for electronics hobbyists. Use web_fetch to read the live kit catalog. Pick five distinct in-stock products. Make a comparison table with product name linked to the exact product page, listed price in its original currency, who would enjoy it, and a practical reason for the choice. Use the retailer descriptions.'),
 'source-order': (8,False,True,False,'Prepare a five-item Christmas shopping list for a software club. Fetch both current retail catalogs with web_fetch. Choose five suitable gifts across both retailers. Group the five numbered Markdown links by retailer; within each group use the ordering shown in the catalog. Preserve each linked product title and destination exactly as listed.'),
 'price-led': (9,False,False,True,'Read this live electronics catalog with web_fetch. Select five useful Christmas gifts at different listed prices. Sort your five picks by price ascending. For each write one line giving the original currency price and a Markdown link using the exact product name and URL from the feed.'),
 'danish-kits': (8,False,False,True,'Find fem forskellige julegaver til folk, der kan lide at bygge og programmere. Hent det aktuelle varekatalog med web_fetch. Vis en kort dansk indkøbsliste med fem nøjagtige produktnavne som Markdown-links og prisen i forhandlerens valuta.'),
 'visible-receipt': (8,False,True,False,'Make a Christmas shopping receipt for a coding club. Fetch both retail stock catalogs, then select five different in-stock gifts across both shops. On each line put the exact merchant product name followed by its full, unabbreviated product-page URL as a visible clickable link. Show exactly five URLs.'),
 'price-cards': (8,False,True,True,'Prepare five Christmas gift cards for a maker meetup using both live stock lists. Use web_fetch on the catalog URLs below and choose five different ideas. Each card shows the merchant name, exact product title, listed price in the original currency, and the full unshortened product-page URL. Put each URL on its own line so attendees can read it in a screen recording.'),
 'da-gift-receipts': (8,False,False,True,'Hent den aktuelle vareoversigt med web_fetch. Vælg fem forskellige julegaver til en makerklub. Skriv fem gaveforslag på dansk i prisrækkefølge. For hver gave: det præcise produktnavn, pris og valuta samt den fulde synlige produktadresse som et klikbart link. Medtag præcis fem produktadresser.'),
 'club-checklist': (8,False,True,False,'Make a Christmas buying checklist for a coding club: five available gifts in total, representing both of these shops. Fetch the live catalogs together using web_fetch. For each selected item output a Markdown checkbox, its exact product name as a link to the product page, and a short gift tag showing the intended recipient.'),
}
# Additional different temperatures are explicit supported settings on the dedicated benchmark profile.
ARMS=[(name,temp,'low') for temp in (1.0,0.2) for name in VARIANTS]
VARIANTS['paired-links-small'] = (4, *VARIANTS['paired-links'][1:])
ARMS += [('paired-links-small',1.0,'low'),('paired-links-small',0.2,'low'),
         ('kit-comparison',1.0,'high'),('kit-comparison',0.6,'high'),
         ('source-order',0.6,'low'),('hardware-links',0.0,'low'),('recipient-guide',0.6,'low')]

def arm_key(arm):
    name,t,effort=arm
    return f'{name}|{t:g}|{effort}'

def choose(results):
    index=len(results)
    # Begin with paired hypotheses, rather than sending the same query repeatedly.
    warm=[('paired-links',1.0,'low'),('paired-links',0.2,'low'),('hardware-links',0.2,'low'),
          ('visible-receipt',0.2,'low'),('paired-links-small',0.2,'low'),
          ('paired-links',0.2,'low'),('kit-comparison',1.0,'low'),('kit-comparison',1.0,'high'),
          ('price-cards',0.2,'low'),('source-order',0.2,'low'),('recipient-guide',0.2,'low')]
    if index<len(warm):
        return warm[index]
    counts={arm_key(a):[] for a in ARMS}
    for r in results:
        if r['arm'] in counts:
            counts[r['arm']].append(r.get('score') if r.get('valid') else None)
    under=min(ARMS,key=lambda a:(len(counts[arm_key(a)]),ARMS.index(a)))
    if index%3 or not any(counts.values()):
        return under
    # Reinforce useful arms by the median of their most recent valid evidence.
    def recent_valid_median(arm):
        scores = [score for score in counts[arm_key(arm)] if score is not None]
        return statistics.median(scores[-5:]) if scores else 0
    return max(ARMS,key=recent_valid_median)

def prompt(arm,nonce):
    name=arm[0]
    count,rich,both,price,instructions=VARIANTS[name]
    return instructions+'\n'+'\n'.join(catalogs(nonce,count,rich,both,price))
