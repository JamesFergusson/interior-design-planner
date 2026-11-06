# Finding products

## Where to look

Search for products sold in the user's country, in their currency, from shops that list a clear price and
dimensions. Prefer the brand's own shop or large retailers with stable product pages. Good starting points:

- UK: John Lewis, Habitat, Made.com, Dunelm, Heal's, Loaf, Swyft, IKEA, B&Q, Wickes, Topps Tiles, Walls and Floors,
  Victorian Plumbing, Lights & Lamps, Farrow & Ball, Little Greene, Dulux.
- US: Crate & Barrel, West Elm, Pottery Barn, Article, Wayfair, IKEA, Home Depot, Lowe's, Rejuvenation,
  Benjamin Moore, Sherwin-Williams.
- EU: IKEA, Maisons du Monde, Bolia, HAY, Muuto, Leroy Merlin, local tile and paint brands.

Search tips: web search may favour US results. Restrict searches to the shops' own domains (`allowed_domains`),
or open a shop's category page directly and pick products from it. Some shops load prices with JavaScript, so the
page text has no price; try the same product at another shop (e.g. Habitat items on habitat.co.uk rather than
argos.co.uk), or choose another product.

Avoid marketplace listings without a stable URL, affiliate or tracking links (strip `utm_` parameters), and
products marked discontinued or out of stock with no date.

## For each option, confirm on the product page

- Exact name, price (and whether it is a sale price), what the price buys (one item, per m², per box and its coverage).
- Overall dimensions. Check they fit: a sofa no wider than the wall it sits on minus 600 mm; coffee table about
  two-thirds of the sofa length; rug large enough for the front legs of the seating; walkways at least 700–900 mm;
  bathroom vanity depth and door swing; kitchen appliance widths matching the units.
- Finish and colour against the scheme.
- Anything a buyer must know: lead time over four weeks, made to order, assembly, delivery cost, bathroom IP rating
  for lights, fire safety labels for children's rooms.

Put the key facts in `spec` (one line) and the one that matters most in `note`.

## Sizes

Record every physical product's overall size in `size`, in millimetres: `w` across the front, `d` front to back,
`h` height. The floor plan draws the product at exactly this size, so take it from the product page or its spec
sheet, not from memory or the name (a "1200 vanity" may be 1190 wide).

- Convert: 60 cm = 600 mm; 23.5 in = 597 mm.
- Shops write sizes in different orders: read the labels (H81.5 x W59.8 x D55 cm is w 598, d 550, h 815). If the
  page gives three unlabelled numbers, it is usually width x depth x height for furniture and width x height for
  mirrors, radiators and towel rails (then `d` is the projection from the wall, if given).
- Shower trays and baths: w is the long side when it sits against a wall along its length.
- Use the size of the variant you priced. If the page has no dimensions, leave `size` out rather than guess; the
  plan then uses the part's own size and says so.
- Set `shape` for round tables, oval baths, quadrant trays and L-shaped sofas.

## Spread of options

Give each part 2–4 options at different price points, with at least one that keeps the room within budget.
If the user named a style or a shop, lead with it. If they own something already, add it as an option with
`price: 0` and put it in `picks`.

## Paint and tiles

- Paint coverage: use the page's figure if it gives one (check whether it is per litre or per tin); otherwise
  assume 12 m² per litre per coat. Two coats: `covers` = m² per tin ÷ 2, e.g. 2.5 L × 12 ÷ 2 = 15.
  In feet: assume 350 ft² per US gallon per coat, so a gallon `can` covers 175 ft² for two coats.
- Tiles: use the price per m² if shown; otherwise price per box with `covers` = m² per box. The part's quantity
  already includes 10% for cutting. Bathroom and kitchen tile areas depend on the layout; set them in `override`.

## Photos

Use the product's main image (the page's `og:image`, or the first large product photo). Download it to
`photos/<option-id>.jpg` and set the option's `"image_file": "photos/<option-id>.jpg"` in room.json:

```bash
curl -L --max-time 20 -A "Mozilla/5.0" -o photos/<option-id>.jpg "<image url>"
```

If the first two downloads fail (blocked or not an image), stop trying for this room. Check the file is a real image (`planner.py check` does this); delete it and leave the option without a photo if
it is not. Never use images from search results that are not the product's own photo. If image downloads are
blocked in this environment, skip photos and tell the user they can add them with "Add photo".
