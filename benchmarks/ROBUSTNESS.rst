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

The current 48 cases comprise six seeds in each of these families:

* Planar profiles, holes, reversed and symmetric extrusion on three planes.
* Boolean cuts, rounded edges, shelling, parent reuse and tags.
* Sketch fillets, subtraction, reuse and opposite extrusion directions.
* Nested assembly add/remove/copy, repeated placements and index consistency.
* STEP/BREP round trips and tessellation index bounds.
* Rotations, large translations, inverse transforms and Boolean differences.

Twelve additional cases check failed-feature retry, iterable stacks, documented
empty-stack errors, malformed selectors, and NaN/infinite dimensions. Focused
regressions additionally exercise failures after native feature creation,
Boolean or cleaning failures, sweep path contexts, interrupts, subclasses,
generator exceptions and every scalar parameter of selected native factories.
Successful features must continue to consume profiles exactly once.

Current checkpoint
------------------

``steve-cad-runtime:api-reliability`` contains CadQuery
``61db43304bc2813cc7e921fde42027c17c6a263b`` and OCCT
``b23819d4579ac85fd6ad4f09dcb48a312096b25c``. It passes 1,409 Python tests,
seven subtests, 78 selected native groups, 48 isolated API scenarios and all
48 Steve model/export audits. Three GUI tests are skipped. All Steve source
hashes, geometry signatures, feature-history results, artifact structures,
placements and mesh settings match the preceding installed package. Raw export
bytes are not required to be identical. See the local reports under ``results/``:

* ``api-reliability-build-provenance.json``
* ``api-reliability-installed-tests.txt``
* ``api-reliability-native-tests.json``
* ``api-reliability-installed-robustness.json``
* ``api-reliability-runtime-validation.json``
* ``api-reliability-geometry-parity.json``

The unpatched OCCT in the development virtual environment fails 57 native
regressions while all Python repository tests pass. The installed candidate
passes those native checks. Kernel-dependent validation must use the matching
candidate image, rather than assuming a source checkout replaces native libraries.

The matched full Steve timing run is in progress. Timing runs must execute
separately from correctness tests, compilers and profilers. Preserve every case,
the alternating order, fresh request processes, mesh settings and input hashes.
Keep measured runtime results distinct from a production failure-rate claim.

Next coverage expansion
-----------------------

Add the free-function module, operators and overload signatures to the inventory.
Expand boundary scenarios to coordinates and axes, offsets, spline/Bezier inputs,
zero-angle twist extrusion, callbacks returning None, partially failing callbacks,
assembly path collisions, generators, copy ownership and serialization failures.
These are review priorities, not claims that all listed behaviors are broken.
Native ownership candidates need isolated sanitizer reproduction and complete
rebuilds of affected callers before an installed fix can be accepted.
