Complete Steve runtime comparison
=================================

All 48 request checks match. Each version has 3 alternating samples
per case, plus warm-up, using a fresh forked child for each request.

Timing scope: ``feature_runtime.run_request; validation and fixture cleanup excluded``.
Installed compiled Steve runtime: yes.

Overall geometric mean: **1.782x**.
Preview: **1.540x**; full builds:
**2.061x**. The reference to preserve is approximately 1.7x.

These are full request timings. The fixed library score is separate.
Medians below 1x remain in the results. Small sample counts do not establish
that a small difference is significant. Summing medians weights slow
cases more heavily and must not replace the geometric mean.

.. list-table:: Median request durations in seconds
   :header-rows: 1

   * - Model
     - Preview before
     - Preview after
     - Speedup
     - Full before
     - Full after
     - Speedup
   * - plate
     - 0.150
     - 0.121
     - 1.237x
     - 0.568
     - 0.324
     - 1.754x
   * - bearing_pedestal
     - 0.685
     - 0.479
     - 1.429x
     - 2.559
     - 1.259
     - 2.033x
   * - design
     - 0.188
     - 0.157
     - 1.198x
     - 0.430
     - 0.297
     - 1.445x
   * - modeling_housing
     - 0.583
     - 0.326
     - 1.790x
     - 1.741
     - 0.658
     - 2.645x
   * - modeling_flange
     - 0.414
     - 0.210
     - 1.974x
     - 2.388
     - 0.794
     - 3.009x
   * - modeling_impeller
     - 3.327
     - 1.739
     - 1.913x
     - 15.212
     - 3.642
     - 4.176x
   * - modeling_sheet_metal_bracket
     - 0.692
     - 0.444
     - 1.561x
     - 1.548
     - 0.905
     - 1.711x
   * - modeling_sheet_metal_return_tray
     - 8.820
     - 4.958
     - 1.779x
     - 16.590
     - 7.253
     - 2.287x
   * - modeling_sheet_metal_enclosure
     - 4.017
     - 2.306
     - 1.742x
     - 8.333
     - 4.804
     - 1.734x
   * - modeling_turbine_stage
     - 6.299
     - 5.425
     - 1.161x
     - 55.821
     - 10.721
     - 5.207x
   * - planetary_gearset
     - 9.477
     - 5.160
     - 1.836x
     - 11.898
     - 7.471
     - 1.593x
   * - turbo_rotor
     - 9.223
     - 5.362
     - 1.720x
     - 11.277
     - 6.607
     - 1.707x
   * - airfoil_wing
     - 0.545
     - 0.388
     - 1.403x
     - 6.691
     - 4.459
     - 1.500x
   * - blocky
     - 2.681
     - 1.626
     - 1.648x
     - 11.518
     - 3.716
     - 3.100x
   * - colored_rack
     - 1.181
     - 0.857
     - 1.378x
     - 3.582
     - 2.976
     - 1.203x
   * - finned_heatsink
     - 1.878
     - 1.345
     - 1.396x
     - 5.198
     - 3.573
     - 1.455x
   * - grooved_pulley
     - 0.149
     - 0.118
     - 1.266x
     - 0.577
     - 0.306
     - 1.885x
   * - helical_auger
     - 0.663
     - 0.490
     - 1.353x
     - 5.694
     - 1.628
     - 3.499x
   * - lofted_duct
     - 0.282
     - 0.193
     - 1.460x
     - 2.125
     - 1.421
     - 1.495x
   * - perforated_panel
     - 5.998
     - 2.414
     - 2.485x
     - 29.787
     - 10.247
     - 2.907x
   * - shelled_enclosure
     - 0.289
     - 0.190
     - 1.521x
     - 1.005
     - 0.509
     - 1.976x
   * - spherical_valve
     - 0.294
     - 0.212
     - 1.384x
     - 1.360
     - 0.952
     - 1.429x
   * - swept_tube
     - 2.529
     - 1.752
     - 1.444x
     - 15.998
     - 8.641
     - 1.852x
   * - varied_linkage
     - 2.323
     - 1.552
     - 1.497x
     - 5.578
     - 3.253
     - 1.715x
