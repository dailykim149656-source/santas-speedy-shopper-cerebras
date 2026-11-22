"""Real shopping variants. Values are catalog endpoints, never product-page answers."""
import json
import statistics

# One live in-stock search per gift category. Each query is fetched during the run; nothing is cached.
SYNTH_CATEGORIES = ('filter', 'mixer', 'oscillator', 'echo', 'cable')
CATEGORY_CATALOGS = {
    'synth-categories': ('aisynthesis.com', SYNTH_CATEGORIES),
    'mercantile-categories': ('mercantile.wordpress.org', ('shirt', 'hoodie', 'mug', 'tumbler', 'golf')),
}

def catalogs(nonce, count, rich=False, shops='both', price=False):
    fields = 'name,permalink'
    if price or rich:
        fields += ',prices'
    if rich:
        fields += ',short_description'
    args = f'per_page={count}&stock_status=instock&_fields={fields}&_run={nonce}'
    if shops in CATEGORY_CATALOGS:
        host, categories = CATEGORY_CATALOGS[shops]
        return [f'https://{host}/wp-json/wc/store/v1/products?search={query}&' + args
                for query in categories]
    if shops in ('synth-sorted', 'synth-sorted-pages'):
        url = ('https://aisynthesis.com/wp-json/wc/store/v1/products?search=eurorack&' + args
               + '&orderby=id&order=asc')
        return [url + f'&offset={offset}' for offset in (0, 3)] if shops == 'synth-sorted-pages' else [url]
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
# These arms test whether shorter instructions or a tool-first workspace instruction
# change the verified shopping result's official mean. Earlier calls differed in
# reasoning length and rate, but the cause of that difference is unknown.
VARIANTS['synth-first-five-short'] = (*VARIANTS['synth-first-five'][:-1],
    'Christmas gifts: web_fetch this live catalog and return its first five items as numbered '
    '[exact name](exact product URL) links.')
VARIANTS['synth-first-five-agents-direct'] = VARIANTS['synth-first-five']
VARIANTS['synth-first-five-short-direct'] = VARIANTS['synth-first-five-short']
# Written as the benchmark workspace's AGENTS.md for these arms only and removed before every other arm.
DIRECT_TOOL_AGENTS_MD = (
    '# Tool-first replies\n\n'
    '- If the message gives a URL to fetch, your first output is the web_fetch call for that exact URL. '
    'Do not think through, plan or restate the request before calling it.\n'
    '- When the result arrives, write the requested answer straight from the fetched data, '
    'with no preamble and no deliberation.\n')
WORKSPACE_AGENTS_BY_VARIANT = {'synth-first-five-agents-direct': DIRECT_TOOL_AGENTS_MD,
                               'synth-first-five-short-direct': DIRECT_TOOL_AGENTS_MD}
FIRST_FIVE_VARIANTS = ('synth-first-five', 'synth-first-five-six', 'synth-first-five-direct-fetch',
                       'synth-first-five-short', 'synth-first-five-agents-direct', 'synth-first-five-short-direct')
# Identical shopping conditions have produced widely different rates. Alternate
# controls with these treatments to limit, but not eliminate, time confounding.
PRIORITY_CONTROL = ('synth-first-five', .2, 'low')
DIRECT_FETCH_ARM = ('synth-first-five-direct-fetch', .2, 'low')
DIRECT_FETCH_VALID, DIRECT_FETCH_MAX_ATTEMPTS = 3, 5
PRIORITY_ARMS = (('synth-first-five-agents-direct', .2, 'low'), ('synth-first-five-short', .2, 'low'),
                 ('synth-first-five-short-direct', .2, 'low'))
PRIORITY_VALID, PRIORITY_MAX_ATTEMPTS = 5, 8
# Test-branch arms adapted from a published competing setup, without its transport patch or cached results:
# a numeric reasoning cap in the workspace instructions, temperature 0, and five parallel live fetches whose
# exact arguments appear in the request. Each step up the ladder adds one change to the previous arm.
DIRECT_TOOL_CAP_AGENTS_MD = (
    '# Tool-first replies\n\n'
    '- Think in at most 5 words.\n'
    '- If the message gives URLs to fetch, your first output is the web_fetch calls for those exact URLs. '
    'Do not plan or restate the request.\n'
    '- When the results arrive, write the requested answer straight from the fetched data, with no preamble.\n')
VARIANTS['synth-first-five-short-cap'] = VARIANTS['synth-first-five-short']
VARIANTS['synth-first-five-short-cap-args'] = (*VARIANTS['synth-first-five-short-cap'][:-1],
    VARIANTS['synth-first-five-short-cap'][-1].replace(
        'web_fetch this live catalog', 'call web_fetch with the exact argument object below'))
MERCANTILE_VARIANT = 'mercantile-five-categories-cap'
for name, shops in (('synth-five-categories-cap', 'synth-categories'), (MERCANTILE_VARIANT, 'mercantile-categories')):
    VARIANTS[name] = (1, False, shops, False,
        'Christmas gifts: call web_fetch 5 times in parallel, once with each exact argument object below. '
        'Then return the one product from each result as numbered [exact name](exact product URL) links, '
        'in the order listed.')
VARIANTS['synth-five-categories-cap-4000'] = VARIANTS['synth-five-categories-cap']
FIRST5027_VARIANTS = ('synth-five-categories-cap', 'first5027-extract-text', 'first5027-defer-answer')
for name in FIRST5027_VARIANTS[1:]:
    VARIANTS[name] = VARIANTS[FIRST5027_VARIANTS[0]]
FIRST5027_DEFER_LINE = (
    'Before any tool results arrive, copy the five supplied argument objects directly into the five '
    'web_fetch calls in order. Defer planning the final answer until the results arrive.')
WORKSPACE_AGENTS_BY_VARIANT.update({
    'first5027-extract-text': DIRECT_TOOL_CAP_AGENTS_MD,
    'first5027-defer-answer': DIRECT_TOOL_CAP_AGENTS_MD + FIRST5027_DEFER_LINE + '\n',
})
SORTED_SIX_INSTRUCTION = (
    'Christmas gifts: call web_fetch once with each exact argument object below, in parallel when there '
    'is more than one. Then return the first five distinct products from the live ordered catalog '
    'candidates as numbered [exact name](exact product URL) links, preserving catalog order and '
    'processing pages in the order listed.')
VARIANTS['synth-six-sorted'] = (6, False, 'synth-sorted', False, SORTED_SIX_INSTRUCTION)
VARIANTS['synth-six-sorted-pages'] = (3, False, 'synth-sorted-pages', False, SORTED_SIX_INSTRUCTION)
EXPERIMENT_1700_VARIANTS = ('synth-five-categories-cap-4000', 'synth-six-sorted', 'synth-six-sorted-pages')
EXACT_ARGS_VARIANTS = FIRST5027_VARIANTS + EXPERIMENT_1700_VARIANTS + (MERCANTILE_VARIANT,)
CATEGORY_VARIANTS = FIRST5027_VARIANTS + ('synth-five-categories-cap-4000', MERCANTILE_VARIANT)
WORKSPACE_AGENTS_BY_VARIANT.update({'synth-first-five-short-cap': DIRECT_TOOL_CAP_AGENTS_MD,
                                    'synth-first-five-short-cap-args': DIRECT_TOOL_CAP_AGENTS_MD,
                                    'synth-five-categories-cap': DIRECT_TOOL_CAP_AGENTS_MD,
                                    MERCANTILE_VARIANT: DIRECT_TOOL_CAP_AGENTS_MD})
WORKSPACE_AGENTS_BY_VARIANT.update({name: DIRECT_TOOL_CAP_AGENTS_MD for name in EXPERIMENT_1700_VARIANTS})
FIRST_FIVE_VARIANTS += ('synth-first-five-short-cap', 'synth-first-five-short-cap-args',
                        'synth-six-sorted', 'synth-six-sorted-pages')
TEST_CONTROL = PRIORITY_CONTROL
TEST_ARMS = (TEST_CONTROL, ('synth-first-five-short-cap', .2, 'low'), ('synth-first-five-short-cap', 0.0, 'low'),
             ('synth-five-categories-cap', 0.0, 'low'))
FOCUS_D5027 = ('synth-five-categories-cap', .2, 'low')
MERCANTILE_ARM = (MERCANTILE_VARIANT, *FOCUS_D5027[1:])
TARGET_ARMS = (FOCUS_D5027, ('synth-five-categories-cap', 0.0, 'low'),
               ('synth-first-five-short-cap-args', .2, 'low'), ('synth-first-five-short-cap', .2, 'low'))
# Five-category focus: three category trials (temperature 0.2, 0, 0.2) per adjacent control trial, with no
# score-based stop. Enabled by a focus-categories marker in the test cache.
FOCUS_CATEGORY_CYCLE = (FOCUS_D5027, ('synth-five-categories-cap', 0.0, 'low'), FOCUS_D5027, TEST_CONTROL)
# Relay arm: the D5027 request, sent through tools/request_relay.mjs, which applies a short system prompt and
# tool settings to every request of the run (retries included): web_fetch forced and parallel on the first
# generation, and no tool definitions on the final one once all five committed fetches returned product data.
# Responses pass through unchanged. Enabled by a focus-relay marker: relay and D5027 control alternate.
RELAY_VARIANTS = ('synth-five-categories-relay',)
VARIANTS['synth-five-categories-relay'] = VARIANTS['synth-five-categories-cap']
EXACT_ARGS_VARIANTS += RELAY_VARIANTS
CATEGORY_VARIANTS += RELAY_VARIANTS
WORKSPACE_AGENTS_BY_VARIANT['synth-five-categories-relay'] = DIRECT_TOOL_CAP_AGENTS_MD
RELAY_SYSTEM_PROMPT = (
    'You are a shopping assistant. Think in at most 5 words. '
    'When the user lists web_fetch argument objects, call web_fetch once per object, all in parallel, '
    'copying each object exactly. Do not plan or restate the request. '
    'When the results arrive, reply with only the requested answer, copied exactly from the fetched data, '
    'with no preamble.')
FOCUS_RELAY_CYCLE = (('synth-five-categories-relay', .2, 'low'), FOCUS_D5027)
# Applied to every test-branch trial, control included, to shrink the quota Cerebras reserves per request.
TEST_MAX_TOKENS = 1024
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
) + PRIORITY_ARMS
ARMS += [arm for arm in RESEARCH_ARMS if arm not in ARMS]
ARMS += [arm for arm in TEST_ARMS if arm not in ARMS]
ARMS += [arm for arm in FOCUS_CATEGORY_CYCLE if arm not in ARMS]
ARMS += [arm for arm in FOCUS_RELAY_CYCLE if arm not in ARMS]
ARMS += [(name, .2, 'low') for name in EXPERIMENT_1700_VARIANTS]
ARMS += [(name, .2, 'low') for name in FIRST5027_VARIANTS if (name, .2, 'low') not in ARMS]

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

def priority_pending(counts):
    """Treatments still short of valid paired runs; a stubbornly failing arm stops after a fixed attempt budget."""
    return [arm for arm in PRIORITY_ARMS
            if sum(score is not None for score in counts[arm_key(arm)]) < PRIORITY_VALID
            and len(counts[arm_key(arm)]) < PRIORITY_MAX_ATTEMPTS]

def choose_test(results):
    """Round-robin over the test ladder; a pre-send failure adds no history row, so that arm is retried."""
    attempts = {arm_key(arm): 0 for arm in TEST_ARMS}
    for row in results:
        if row['arm'] in attempts:
            attempts[row['arm']] += 1
    return min(TEST_ARMS, key=lambda arm:(attempts[arm_key(arm)], TEST_ARMS.index(arm)))

def choose_d5027(_results):
    return FOCUS_D5027

def choose_category_focus(results):
    """Walk the focus cycle by completed trials of its arms; a pre-send failure adds no row and retries the slot."""
    cycle = {arm_key(arm) for arm in FOCUS_CATEGORY_CYCLE}
    done = sum(1 for row in results if row['arm'] in cycle)
    return FOCUS_CATEGORY_CYCLE[done % len(FOCUS_CATEGORY_CYCLE)]

def choose_relay_focus(results):
    """Alternate relay and control. A run that only hit a rate limit made no measurement, so its slot repeats."""
    cycle = {arm_key(arm) for arm in FOCUS_RELAY_CYCLE}
    done = sum(1 for row in results if row['arm'] in cycle and not (row.get('rate_limited') and not row.get('call_count')))
    return FOCUS_RELAY_CYCLE[done % len(FOCUS_RELAY_CYCLE)]

def choose_target(results):
    """Balance focused arms by completed attempts, prioritizing category fetches when tied."""
    attempts = {arm_key(arm): 0 for arm in TARGET_ARMS}
    for row in results:
        if row['arm'] in attempts:
            attempts[row['arm']] += 1
    return min(TARGET_ARMS, key=lambda arm:(attempts[arm_key(arm)], TARGET_ARMS.index(arm)))

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
    # Recheck the promising first-call result against adjacent control runs.
    # A pre-send failure adds no history row and retries this arm.
    direct_attempts = counts[arm_key(DIRECT_FETCH_ARM)]
    if (len(direct_attempts) < DIRECT_FETCH_MAX_ATTEMPTS
            and sum(score is not None for score in direct_attempts) < DIRECT_FETCH_VALID):
        return PRIORITY_CONTROL if index % 2 else DIRECT_FETCH_ARM
    pending = priority_pending(counts)
    if pending:
        if index % 2:
            return PRIORITY_CONTROL
        return min(pending, key=lambda arm:(len(counts[arm_key(arm)]), PRIORITY_ARMS.index(arm)))
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
    urls = catalogs(nonce,count,rich,shops,price)
    if name == 'synth-first-five-short-cap-args':
        urls = [json.dumps({'url': url, 'extractMode': 'text', 'maxChars': 20000},
                           separators=(',', ':')) for url in urls]
    elif name == 'synth-five-categories-cap-4000':
        urls = [json.dumps({'url': url, 'extractMode': 'text', 'maxChars': 4000},
                           separators=(',', ':')) for url in urls]
    elif name == 'first5027-extract-text':
        urls = [json.dumps({'url': url, 'extractMode': 'text'},
                           separators=(',', ':')) for url in urls]
    elif name in EXACT_ARGS_VARIANTS:
        # Spell out each web_fetch argument object so the tool call can be copied from the request.
        urls = [json.dumps({'url': url}, separators=(',', ':')) for url in urls]
    return instructions+'\n'+'\n'.join(urls)
