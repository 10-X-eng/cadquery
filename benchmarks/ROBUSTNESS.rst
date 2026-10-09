CadQuery reliability validation
==============================

The current goal is practical reliability across the public API and unusual
modeling sequences while preserving Steve's approximately 1.7x speed gain.
Geometry, precision, topology, feature history and requested export quality
remain gates. Work belongs to the user's forks; upstream PRs are prohibited.

Run the deterministic workflow harness with the intended interpreter::

    python benchmarks/api_robustness.py --source . --output /tmp/api-results.json

Omit ``--source`` to test the installed package. Each scenario runs in a fresh
process with one native thread, a 20-second timeout and an 8 GiB address-space
limit after importing dependencies. A timeout, signal, unexpected exception,
invalid BRep or a failed geometric invariant fails the scenario. Nonfinite-input
scenarios require an exception; valid geometry returned from invalid input is
also rejected. Reports include API inventory, visited Python members and a hash
of the harness. Visited members include internal incidental calls and must not
be interpreted as exhaustive behavior coverage. The inventory includes inherited
members separately for each class; it is not a count of distinct API functions.
The inventory now includes constructors, operators, free functions, CQGI, and
multimethod overload signatures.

The current 56 cases comprise six seeds in each of these families:

* Planar profiles, holes, reversed and symmetric extrusion on three planes.
* Boolean cuts, rounded edges, shelling, parent reuse and tags.
* Sketch fillets, subtraction, reuse and opposite extrusion directions.
* Nested assembly add/remove/copy, repeated placements and index consistency.
* STEP/BREP round trips and tessellation index bounds.
* Rotations, large translations, inverse transforms and Boolean differences.

Twenty additional cases check failed-feature retry, iterable stacks, documented
empty-stack errors, malformed selectors, NaN/infinite dimensions, omitted callback
results, partial callback failures, callback prototype ownership, failed wire
closure, zero-angle twist extrusion, assembly path collisions, free functions,
and operators. Focused regressions additionally exercise failures after native
feature creation,
Boolean or cleaning failures, sweep path contexts, interrupts, subclasses,
generator exceptions and every scalar parameter of selected native factories.
Successful features must continue to consume profiles exactly once. Guarded
operations run in their own frame, so tracers, profilers and Steve's feature
history recorder see the operation's name and bound arguments.

Current checkpoint
------------------

``steve-cad-runtime:api-stateful`` contains CadQuery
``40730cad8bddbcd2d35a522b8226a564f8fd78c4`` and OCCT
``b23819d4579ac85fd6ad4f09dcb48a312096b25c``. It passes 1,548 Python tests,
seven subtests, 78 selected native groups, 56 isolated API scenarios and all
48 Steve model/export audits. Three GUI tests are skipped. All Steve source
hashes, geometry signatures, feature-history results, artifact structures,
placements and mesh settings match the preceding installed package. Raw export
bytes are not required to be identical. See the local reports under ``results/``:

* ``api-stateful-installed-tests.txt``
* ``api-stateful-build-provenance.json``
* ``api-stateful-native-tests.json``
* ``api-stateful-installed-robustness.json``
* ``api-stateful-runtime-validation.json``
* ``api-stateful-geometry-parity.json``

The new 139 focused tests fail 115 times on the preceding CadQuery package and
all pass on this revision. Regression coverage includes three coordinate planes,
reversed extrusion, local/global callbacks, five combining modes, reused shapes,
interrupts, owned subassembly edits and rotated placement of each stack type.
The global ``eachpoint`` composition now applies the local placement before the
workplane frame. Callback results of None follow the documented ``each`` contract.
Failure recovery preserves the shared context's original lists and cursor.
Assembly collision checks happen before changing any ancestor index.

The unpatched OCCT in the development virtual environment fails 57 native
regressions while all Python repository tests pass. The installed candidate
passes those native checks. Kernel-dependent validation must use the matching
candidate image, rather than assuming a source checkout replaces native libraries.

The current matched full Steve timing run records **1.782x overall** across
all 48 cases, retaining the approximately 1.7x reference. All geometry checks
match and all case medians improve over original Steve. Three alternating
samples plus warm-up use fresh forked children, one native thread and CPU 0.
See ``results/api-stateful-installed-runtime-summary.rst`` and its JSON/raw
siblings. This is a run-level observation, not a guarantee for every possible
API sequence or platform. Timing runs execute separately from correctness
tests, compilers and profilers. Preserve every case,
the alternating order, fresh request processes, mesh settings and input hashes.
Keep measured runtime results distinct from a production failure-rate claim.

The five-case stress comparison against the preceding package passes all geometry
checks. Its nine-sample case ratios range from 0.962x to 1.096x, including 0.962x
for copying callback results to prevent mutation of shared prototypes. That
stress score is not the full Steve performance gate.

Coverage expansion
------------------

Six further isolated cases cover the previously listed review priorities:

* ``plane_frames``: every named plane and its classmethod, orthonormal frames,
  local/world round trips at large coordinates, explicit and turned x
  directions, rotation, plane independence and invalid frames.
* ``location_axes``: composition order, inverses, powers, plane locations,
  points on an offset rotated workplane (``pushPoints`` and local
  ``eachpoint``), affine matrices with non-uniform scale, an arbitrary revolve
  axis and a zero rotation axis.
* ``offsets``: arc, intersection and inward wire offsets, a collapsing offset,
  circle and Workplane offsets, inward/outward/closed solid shells, a shell of a
  located box and of a located sphere, face thickening and a NaN thickness.
* ``splines``: interpolation through points, end tangents, periodic and
  parameterized splines, approximation with and without smoothing, cubic
  Bezier evaluation, Workplane and Sketch spline/Bezier solids and refused
  degenerate, NaN and mismatched inputs.
* ``copy_ownership``: shape copies and moves, Vector results that never alias
  their inputs, tuple values, Location/Plane/Workplane/Sketch/Assembly copies
  and pickling of shapes, vectors, locations, planes and matrices.
* ``serialization_failures``: exports into a missing directory, unknown export
  types, empty/garbage/truncated STEP, BREP, binary and pickle inputs, in-memory
  BREP/binary round trips, assembly STEP export and an empty compound.

All six pass on this fork with OCP 8.0.1.1, with and without the companion
OCCT toolkits. Upstream ``9a6a705`` fails two of them: ``Vector.transform``
raises for a non-orthogonal matrix, and ``hollow`` of a located sphere raises
``StdFail_NotDone``. ``Workplane(plane)`` keeps the caller's ``Plane`` object
(upstream behavior); every derived workplane holds its own copy.

``Standard_Handle`` assignment from an owned child can destroy the new object
too early; move assignment can leave an ownership cycle. A source correction and
registered lifetime GTests pass 26 native checks, with the 12 basic/lifetime
checks also passing under ``OCCT_HANDLE_NOCAST``. These are source-only checks
on the separate ``steve/handle-lifetime-reliability`` OCCT branch. The correction
is committed as ``6003228c5`` and is not included in the installed image above.
This header is instantiated in callers; replacing one toolkit cannot establish
that all native libraries and Python bindings use it. A Steve runtime image
with only the six fork toolkits replaced (OCP 8.0.1.1 not rebuilt) matches the
same image without them on all 286 Steve geometry/export parity builds and
every Steve suite, and its build times are unchanged (1.423x versus 1.420x over
the original Steve runtime). The OCP rebuild needed to bring this header into
the bindings remains outstanding.
