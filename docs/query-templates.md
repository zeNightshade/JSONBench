# Query template subset

Translation now validates a deliberately small subset rather than silently accepting
unsupported syntax. Compilation never mutates the input template.

Order: inner joins, array unnesting, equality filtering, grouping, projection,
sorting, limit. Collection identifiers are simple names; field paths are dot-separated
identifiers. SQL++ identifiers are quoted and scalar values encoded as JSON literals.

Supported aggregation: sum/avg/min/max over a field or size(field), and count(*).
Arbitrary functions, aggregate-over-aggregate expressions, and malformed trailing
syntax are rejected. The scalar size expression requires an actual array.

`match` currently accepts non-null scalar equality only. Null/missing predicates,
operator dictionaries, and nonfinite values fail explicitly pending a common semantic
contract. Scalar fields should have the same declared type in both databases;
heterogeneous type coercion is not validated.

`project` supports inclusion mappings such as `{"name": 1}` before grouping only.
Post-group projection and exclusion projections are rejected. Native output shapes
are not identical (MongoDB retains _id by default; SQL++ aliases projected paths).
Correctness comparison must normalise those shapes explicitly.

`sort` is `{"field": "name", "direction": 1}` or direction -1 in both generators.
After grouping, only aggregate aliases can be sorted. With projection, sorting must
reference an included field. Limits are strictly positive integers; ties require an
explicit deterministic ordering before result equivalence can be asserted.

Join results are flattened, producing inner-join behaviour; duplicate matches retain
multiplicity. Unnest aliases are resolved by exact path prefixes, not character
stripping. The current benchmark assumes existing, correctly typed arrays, and
non-null scalar join keys. Missing/scalar array behaviour is not claimed equivalent.

## Open semantic decisions

Q8 currently joins all bookings and all reviews for a tour, then expands travellers.
This preserves the original template, including its cross-product weighting. It is
not necessarily the intended meaning of a destination rating by traveller nationality.
An alternative is to associate each review with its own booking via booking_id.
Resolve the research question before changing that query.

Q4 counts matching unnested itinerary entries. Repeated visits to the same location
can count a tour more than once. Decide whether the intended metric is visits or
distinct tours. Its fixed location literal may also produce zero matches on generated
data; parameter selection/selectivity must be validated before benchmarking.

Q3 averages booking array sizes directly; it does not unnest travellers. Update the
paper's operator table accordingly.

Unit tests check the compiler subset, alias resolution, immutability, escaping, and
all eight templates. They are not evidence of cross-system result equivalence. The eight benchmark queries also pass independent expected-answer
[live fixture checks](live-validation.md). Generated-data validation and edge cases
outside the documented subset remain required.
