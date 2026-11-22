"""Real shopping variants. Values are catalog endpoints, never product-page answers."""
import statistics

def catalogs(nonce, count, rich=False, shops='both', price=False):
    fields = 'name,permalink'
    if price or rich:
        fields += ',prices'
    if rich:
        fields += ',short_description'
    args = f'per_page={count}&stock_status=instock&_fields={fields}&_run={nonce}'
    wordpress = 'https://mercantile.wordpress.org/wp-json/wc/store/v1/products?' + args
    hardware = 'https://raspberrypi.dk/wp-json/wc/store/v1/products?search=kit&' + args
    synth = 'https://aisynthesis.com/wp-json/wc/store/v1/products?search=eurorack&' + args
    return {'both':[wordpress,hardware],'wordpress':[wordpress],'hardware':[hardware],
            'synth':[synth],'wordpress-synth':[wordpress,synth]}[shops]

# Each arm describes a useful user-facing shopping result and a real choice between candidates.
VARIANTS = {
 'paired-links': (8,False,'both',False,'Find five different Christmas gifts for people who enjoy making things. Use web_fetch on both in-stock retail catalogs in parallel. Include both shops. Return a numbered Markdown list with the exact product titles linked to their exact product pages.'),
 'hardware-links': (10,False,'hardware',False,'Find five distinct real Christmas gifts suitable for hobby electronics from this live retailer. Fetch the catalog once with web_fetch and select five useful gifts for different projects. Return five numbered product titles as Markdown links to their actual product pages.'),
 'recipient-guide': (6,True,'both',False,'Build a Christmas gift guide for a hybrid team of bloggers and hardware hobbyists. Use web_fetch in parallel on both live merchant stock lists. Choose five different items across the shops. For each give a Markdown link with the exact merchant title, its listed price in the original currency, and one concrete recipient or use case supported by the item. Keep the guide easy to scan.'),
 'kit-comparison': (8,True,'hardware',False,'A family is shopping for five Christmas gifts for electronics hobbyists. Use web_fetch to read the live kit catalog. Pick five distinct in-stock products. Make a comparison table with product name linked to the exact product page, listed price in its original currency, who would enjoy it, and a practical reason for the choice. Use the retailer descriptions.'),
 'source-order': (8,False,'both',False,'Prepare a five-item Christmas shopping list for a software club. Fetch both current retail catalogs with web_fetch. Choose five suitable gifts across both retailers. Group the five numbered Markdown links by retailer; within each group use the ordering shown in the catalog. Preserve each linked product title and destination exactly as listed.'),
 'price-led': (9,False,'hardware',True,'Read this live electronics catalog with web_fetch. Select five useful Christmas gifts at different listed prices. Sort your five picks by price ascending. For each write one line giving the original currency price and a Markdown link using the exact product name and URL from the feed.'),
 'danish-kits': (8,False,'hardware',True,'Find fem forskellige julegaver til folk, der kan lide at bygge og programmere. Hent det aktuelle varekatalog med web_fetch. Vis en kort dansk indkøbsliste med fem nøjagtige produktnavne som Markdown-links og prisen i forhandlerens valuta.'),
 'visible-receipt': (8,False,'both',False,'Make a Christmas shopping receipt for a coding club. Fetch both retail stock catalogs, then select five different in-stock gifts across both shops. On each line put the exact merchant product name followed by its full, unabbreviated product-page URL as a visible clickable link. Show exactly five URLs.'),
 'price-cards': (8,False,'both',True,'Prepare five Christmas gift cards for a maker meetup using both live stock lists. Use web_fetch on the catalog URLs below and choose five different ideas. Each card shows the merchant name, exact product title, listed price in the original currency, and the full unshortened product-page URL. Put each URL on its own line so attendees can read it in a screen recording.'),
 'da-gift-receipts': (8,False,'hardware',True,'Hent den aktuelle vareoversigt med web_fetch. Vælg fem forskellige julegaver til en makerklub. Skriv fem gaveforslag på dansk i prisrækkefølge. For hver gave: det præcise produktnavn, pris og valuta samt den fulde synlige produktadresse som et klikbart link. Medtag præcis fem produktadresser.'),
 'club-checklist': (8,False,'both',False,'Make a Christmas buying checklist for a coding club: five available gifts in total, representing both of these shops. Fetch the live catalogs together using web_fetch. For each selected item output a Markdown checkbox, its exact product name as a link to the product page, and a short gift tag showing the intended recipient.'),
}
# Additional different temperatures are explicit supported settings on the dedicated benchmark profile.
ARMS=[(name,temp,'low') for temp in (1.0,0.2) for name in VARIANTS]
VARIANTS['paired-links-small'] = (4, *VARIANTS['paired-links'][1:])
VARIANTS['source-order-compact'] = (8, False, 'both', False,
    'Fetch both live catalogs. Pick five distinct Christmas gifts for a software club from both stores. Return just five numbered [exact product name](exact product page) links, keeping the items in their catalog order.')
VARIANTS['wordpress-links'] = (8, False, 'wordpress', False,
    'Fetch the live retailer catalog with web_fetch. Pick five distinct Christmas gifts for a software club. Return just five numbered [exact product name](exact product page) links, keeping the items in their catalog order.')
VARIANTS['synth-links'] = (8, False, 'synth', False, VARIANTS['wordpress-links'][-1])
VARIANTS['synth-links-temp-zero'] = VARIANTS['synth-links']
VARIANTS['synth-links-temp-one'] = VARIANTS['synth-links']
VARIANTS['synth-links-six'] = (6, *VARIANTS['synth-links'][1:])
VARIANTS['synth-first-five'] = (*VARIANTS['synth-links'][:-1], VARIANTS['synth-links'][-1].replace(
    'Pick five distinct Christmas gifts for a software club.',
    'For a software club, choose the first five distinct gifts in this in-stock Christmas gift catalog.'))
VARIANTS['synth-first-five-six'] = (6, *VARIANTS['synth-first-five'][1:])
VARIANTS['synth-first-five-direct-fetch'] = (*VARIANTS['synth-first-five'][:-1],
    VARIANTS['synth-first-five'][-1].replace(
        'Fetch the live retailer catalog with web_fetch.',
        'First call web_fetch once with the catalog URL below, extractMode "text", and maxChars 20000.'))
VARIANTS['synth-links-brief'] = (8, False, 'synth', False,
    'Fetch the live catalog with web_fetch. Pick five distinct Christmas gifts for a software club. '
    'Return five numbered links in catalog order with exact product titles and page URLs.')
CONTEXT_INJECTION_BY_VARIANT = {'synth-links-no-workspace': 'never'}
VARIANTS['synth-links-no-workspace'] = VARIANTS['synth-links']
VARIANTS['synth-table'] = (8, False, 'synth', False,
    'Fetch the live retailer catalog with web_fetch. Pick five distinct Christmas gifts for a software club. '
    'Return a one-column Markdown table named Gift with five [exact product name](exact product page) links, '
    'keeping the items in their catalog order.')
VARIANTS['synth-autolinks'] = (8, False, 'synth', False,
    'Fetch the live retailer catalog with web_fetch. Pick five distinct Christmas gifts for a software club. '
    'Return just five numbered lines in catalog order, each with the exact product name followed by its exact '
    'product page URL in Markdown angle brackets.')
VARIANTS['source-order-synth'] = (8, False, 'wordpress-synth', False, VARIANTS['source-order'][-1])
PRICE_TASK = ('Use web_fetch to open the live catalog. Choose five distinct in-stock Christmas gifts for a software '
              'club in catalog order. Give the exact product title linked to its exact product page and the listed price '
              'with its currency for every gift. ')
VARIANTS['research-table'] = (8, False, 'wordpress', True, PRICE_TASK +
    'Use only a Markdown table with the two columns Gift and Price and five product rows.')
VARIANTS['research-prose'] = (8, False, 'wordpress', True, PRICE_TASK +
    'Use five short sentences, one per gift, with no table or list.')
VARIANTS['research-price-total'] = (8, False, 'wordpress', True, PRICE_TASK +
    'Use five short sentences, one per gift, with no table or list. After each price state the running subtotal '
    'for one unit of each gift listed so far, excluding shipping and tax. Put the subtotal on the same line '
    'as its gift link, using the words Subtotal USD followed by the amount to two decimal places.')
VARIANTS['research-reasoning-max'] = VARIANTS['source-order']
TOP_P_BY_VARIANT = {'source-order-top-p-080': 0.8, 'source-order-top-p-045': 0.45}
for name in TOP_P_BY_VARIANT:
    VARIANTS[name] = VARIANTS['source-order']
MAX_TOKENS_BY_VARIANT = {'source-order-max-2048': 2048, 'research-cap-4096': 4096}
for name in MAX_TOKENS_BY_VARIANT:
    VARIANTS[name] = VARIANTS['source-order']
ARMS += [('paired-links-small',1.0,'low'),('paired-links-small',0.2,'low'),
         ('kit-comparison',1.0,'high'),('kit-comparison',0.6,'high'),
         ('source-order',0.6,'low'),('hardware-links',0.0,'low'),('recipient-guide',0.6,'low'),
         ('source-order-compact',0.2,'low'),('wordpress-links',0.2,'low'),
         ('synth-links',0.2,'low'),('source-order-synth',0.2,'low')]
ARMS += [(name, 0.2, 'low') for name in TOP_P_BY_VARIANT]
ARMS += [(name, 0.2, 'low') for name in MAX_TOKENS_BY_VARIANT]
RESEARCH_ARMS = (
    ('synth-links', .2, 'low'), ('wordpress-links', .2, 'low'),
    ('synth-links-six', .2, 'low'), ('synth-links-temp-zero', 0.0, 'low'),
    ('synth-table', .2, 'low'), ('synth-autolinks', .2, 'low'), ('synth-first-five', .2, 'low'),
    ('synth-links-brief', .2, 'low'), ('synth-links-no-workspace', .2, 'low'),
    ('synth-links-temp-one', 1.0, 'low'), ('synth-first-five-six', .2, 'low'),
    ('synth-first-five-direct-fetch', .2, 'low'),
    ('source-order-synth', .2, 'low'), ('source-order', .2, 'low'),
    ('research-table', .2, 'low'), ('research-prose', .2, 'low'),
    ('paired-links-small', .2, 'low'), ('paired-links', .2, 'low'),
    ('research-reasoning-max', .2, 'max'),
    ('source-order-max-2048', .2, 'low'), ('research-cap-4096', .2, 'low'),
)
ARMS += [arm for arm in RESEARCH_ARMS if arm not in ARMS]

def arm_key(arm):
    name,t,effort=arm
    return f'{name}|{t:g}|{effort}'

def preferred_arm(counts):
    measured = []
    for arm in ARMS:
        attempts = counts[arm_key(arm)][-5:]
        valid = [score for score in attempts if score is not None]
        if valid:
            measured.append((arm, attempts, valid))
    if not measured:
        return None
    repeated = [row for row in measured if len(row[2]) >= 3]
    best = max(repeated or measured, key=lambda row:(
        statistics.median(row[2]), len(row[2])/len(row[1]), len(row[2])))
    # Reproduce a new lead. A successful repeat can restore an arm after older failures.
    challengers = [row for row in measured if len(row[2]) < 3
                   and (len(row[1]) < 4 or len(row[2]) == 2 and row[1][-1] is not None)
                   and statistics.median(row[2]) > statistics.median(best[2])]
    if challengers:
        return max(challengers, key=lambda row:statistics.median(row[2]))[0]
    return best[0]

def under_repeated_peak(results, counts):
    eligible = (row for row in results if row['arm'] in counts and row.get('valid')
                and row.get('method_valid') is not False and row.get('score') is not None)
    peak = max(eligible, key=lambda row:row['score'], default=None)
    if peak is None:
        return None
    key = peak['arm']
    if sum(score is not None for score in counts[key]) >= 3 or any(row['arm'] == key for row in results[-12:]):
        return None
    return next(arm for arm in ARMS if arm_key(arm) == key)

def choose(results):
    index=len(results)
    # Begin with paired hypotheses, rather than sending the same query repeatedly.
    warm=[('paired-links',1.0,'low'),('paired-links',0.2,'low'),('hardware-links',0.2,'low'),
          ('visible-receipt',0.2,'low'),('paired-links-small',0.2,'low'),
          ('paired-links',0.2,'low'),('kit-comparison',1.0,'low'),('kit-comparison',1.0,'high'),
          ('price-cards',0.2,'low'),('source-order',0.2,'low'),('recipient-guide',0.2,'low'),
          ('source-order',0.2,'low'),('source-order-compact',0.2,'low'),('wordpress-links',0.2,'low'),
          ('source-order-top-p-080',0.2,'low'),('source-order-top-p-045',0.2,'low'),
          ('source-order-max-2048',0.2,'low'),('source-order',0.2,'low'),('source-order',0.2,'low')]
    if index<len(warm):
        return warm[index]
    counts={arm_key(a):[] for a in ARMS}
    for r in results:
        if r['arm'] in counts:
            adopted = r.get('valid') and r.get('method_valid') is not False
            counts[r['arm']].append(r.get('score') if adopted else None)
    # Reserve one slot in three for comparison; spend the others on the measured leader.
    best = preferred_arm(counts)
    # After repeated failed sessions, sample a new treatment before reusing the leader.
    recent_failures = len(results) >= 3 and not any(r.get('valid') for r in results[-3:])
    if best is not None and not recent_failures and (index % 3 != 0 or len(counts[arm_key(best)]) == 1):
        return best
    # Give a stale, sparsely reproduced record another comparison slot after a healthy sequence.
    if all(row.get('valid') for row in results[-3:]):
        peak = under_repeated_peak(results, counts)
        if peak is not None:
            return peak
    # Rotate the treatment order between passes to reduce time-of-day confounding.
    for repetitions in range(5):
        offset = repetitions % len(RESEARCH_ARMS)
        for arm in RESEARCH_ARMS[offset:] + RESEARCH_ARMS[:offset]:
            if len(counts[arm_key(arm)]) <= repetitions:
                return arm
    return min(ARMS,key=lambda a:(len(counts[arm_key(a)]),ARMS.index(a)))

def prompt(arm,nonce):
    name=arm[0]
    count,rich,shops,price,instructions=VARIANTS[name]
    return instructions+'\n'+'\n'.join(catalogs(nonce,count,rich,shops,price))
