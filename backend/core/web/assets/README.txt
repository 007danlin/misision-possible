Visual resources are copied from the Ostrovok.ru webarchive supplied by the user
on 2026-10-27 for the Ostrovok hackathon prototype.

ostrovok.svg: Ostrovok logo from the archive.
root-regular/medium/bold.woff2: PT Root UI Web fonts from the archive.
root-regular/bold.ttf: same archive fonts decoded from WOFF2 with FontTools
4.60.1 for PDF embedding (glyphs and names unchanged). Recreate with
TTFont('root-regular.woff2'), set font.flavor=None, then font.save(...).
spoof-medium.woff2: Spoof Medium font from the archive.
stay-a.webp: Vertical We&I Lesnaya image from the archive (original resource 37).
stay-b.jpg: Intourist Kolomenskoe image from the archive (original resource 33).
stay-c.jpg: Vertical We&I Moskovskaya image from the archive (original resource 39).

Images are illustrative ONLY; they do not depict hotels in the synthetic
A/B/C travel catalogue. The UI explicitly labels them as illustrations and
never derives hotel names, ratings, prices or availability from these assets.

Homepage home-* images: extracted from the user-supplied Ostrovok.ru webarchive on 2026-10-27 for the local hackathon prototype. Live hotel images are loaded directly from cdn.ostrovok.ru and are not bundled.

Initial inspiration cards destination photographs (2026-10-27):
idea-sochi.jpg: https://ontheworldmap.com/russia/city/sochi/sochi-4.jpg
idea-kazan.jpg: https://s0.rbk.ru/v6_top_pics/media/img/2/67/755347576603672.jpg
idea-petersburg.jpg: https://3.bp.blogspot.com/-mC-PKQUjPY4/UyMfw9WwdQI/AAAAAAAAGTU/rY96AgZHYtA/s1600/7200386802_9b183d61c9_z.jpg
These illustrate destinations, not hotel offers. Source rights remain with their respective owners.

Waiting animation photographs (2026-10-28):
travel-cards/01.webp through 24.webp are 24 distinct Unsplash travel photographs,
downloaded under https://unsplash.com/license (free commercial/non-commercial use,
including copying, modification and distribution). Exact source URLs are retained
in travel-cards/sources.json. These decorative images are not hotel offers.
Optimized to 320x224 WebP, quality 76; the entire pool is approximately 250 KB.
The browser preloads and decodes the local pool on page entry. No Unsplash API,
remote image requests, or image generation are used during the waiting animation.

Direction landscape photographs (2026-10-28):
directions/karelia.jpg, altai.jpg and seliger.jpg are Wikimedia Commons 960px
thumbnails of the actual regions. Exact sources, authors and licenses are in
directions/sources.json. Credits and license links are visible on each card.
Files are unchanged thumbnails; the UI crops their display with object-fit: cover.
These illustrate destinations, not accommodation or the season of a future trip.

All 21 direction catalogue entries have dedicated local destination photographs.
The additional 15 photographs show the named city, coast, park or waterfall;
none are accommodation interiors. See directions/sources.json for exact source,
author and license. A UI coverage test rejects missing or undecodable images.
Legacy saved cards with a null photo_key resolve by direction ID.
