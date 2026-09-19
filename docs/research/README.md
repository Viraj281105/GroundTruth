# Research

Reading notes and literature relevant to the method.

## Core references

- Abadie, Diamond & Hainmueller (2010). *Synthetic Control Methods for
  Comparative Case Studies*. JASA 105(490).
- Abadie (2021). *Using Synthetic Controls: Feasibility, Data Requirements, and
  Methodological Aspects*. Journal of Economic Literature 59(2).
- Duchi, Shalev-Shwartz, Singer & Chandra (2008). *Efficient Projections onto
  the L1-Ball*. ICML.
- Beck & Teboulle (2009). *A Fast Iterative Shrinkage-Thresholding Algorithm*.
  SIAM Journal on Imaging Sciences 2(1).
- Phipson & Smyth (2010). *Permutation P-values Should Never Be Zero*.
  Statistical Applications in Genetics and Molecular Biology 9(1).
- West, Börner, Sills & Kontoleon (2020). *Overstated carbon emission reductions
  from voluntary REDD+ projects*. PNAS 117(39).
- Guizar-Coutiño et al. (2022). *A global evaluation of the effectiveness of
  voluntary REDD+ projects*. Conservation Biology 36(6).
- Huete et al. (2002). *Overview of the radiometric and biophysical performance
  of the MODIS vegetation indices*. Remote Sensing of Environment 83(1–2).

## Open questions

Things we do not yet have a good answer to. Each is a candidate for a research
note once someone digs in.

1. **Donor pools for very large projects.** How should a donor pool be
   constructed when a project is large enough that no comparable unprotected
   unit exists? Kariba at 785,000 ha may be near that limit, and the convex-hull
   assumption fails quietly rather than loudly.
2. **Cross-sensor calibration over 20 years.** What is the defensible approach
   for an NDVI series spanning Landsat 5 through Sentinel-2 when overlap years
   are few? This is the most likely source of a spurious finding.
3. **Bounding leakage beyond the belt.** Currently acknowledged as a limitation.
   Is there a way to bound it rather than only name it?
4. **Indicator selection per ecosystem.** Choosing NDVI vs EVI vs forest area by
   hand per case does not scale and invites motivated choice. What is the
   defensible rule?
5. **How wide is too wide.** A propagated index-to-carbon interval will be
   large. At what width does an honest interval stop being decision-useful, and
   what should the system say at that point?

## Adding a note

One Markdown file per topic. State the question, what was found, what remains
open, and what it implies for the implementation. A note that does not change
what we build is a bookmark, not research.
