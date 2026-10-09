.. _occ_compat:

Running code written for OCP 7
==============================

CadQuery runs on OCP 8 (OCCT 8). OCP 8 renamed or dropped some names that scripts
calling OCP directly may use, so such a script can stop with an ``ImportError`` or
``AttributeError``. :mod:`cadquery.occ_compat` puts those names back.

It is **opt-in**: importing CadQuery changes nothing. Call :func:`cadquery.occ_compat.enable`
once, before the old code runs::

    from cadquery import occ_compat

    occ_compat.enable()

    from OCP.TColgp import TColgp_Array1OfPnt   # OCP 7 name, now OCP.collections.Array1_gp_Pnt
    from OCP.TopoDS import TopoDS

    face = TopoDS.Face_s(shape)                 # OCP 8: TopoDS.Face(shape)

What it restores:

* ``_s`` names of static methods and of namespace functions such as ``TopoDS.Face_s``,
  which OCP 8 binds as ``TopoDS.Face``. Each ``Foo_s`` is the same callable as ``Foo``.
* The package collection names (``TopTools_ListOfShape``, ``TColStd_Array1OfReal``,
  ``TColgp_Array2OfPnt``, ``TDF_LabelSequence`` and about 570 more) in their old modules,
  as aliases of the ``OCP.collections`` classes OCP 8 binds instead, and classes OCCT 8
  renamed (``GCE2d_MakeSegment`` is ``GC_MakeSegment2d``).
* Enum values nested in classes, such as ``AIS_PointCloud.DM_Points``.
* ``Bnd_Box.Get()`` and ``Bnd_Box2d.Get()``: OCP 8.0.1 cannot return their result. The
  restored version returns ``(xmin, ymin, zmin, xmax, ymax, zmax)`` as before; the tuple
  also has OCCT 8's field names (``Xmin``, ``Xmax`` ...).
* ``BRepTopAdaptor_FClass2d``, which OCP 8 no longer binds, as a Python class with the
  same constructor and ``Perform``, ``PerformInfinitePoint`` and ``TestOnRestriction``. It
  follows OCCT's algorithm and gives the same answers as the OCP 7.9 class.

``enable()`` only adds names; what OCP 8 already defines keeps working as it is (``Get()``
is replaced only because its OCP 8 binding cannot return). It is idempotent and
thread-safe. ``occ_compat.restored()`` lists what it set.

Not restored, because OCP 8 does not bind them or OCCT 8 removed them: collection
instantiations OCP 8 has no class for (for example ``BRepCheck_ListOfStatus``), removed
classes (``LProp3d_*``, ``PLib_Base``, ``GProp_EquaType``, ``TopTools_MutexForShapeProvider``,
``BRepMesh_FactoryError``), and methods OCCT 8 removed (``Standard_ErrorHandler.LastCaughtError``,
``BRepAdaptor_Surface.ChangeSurface``). New code should use the OCP 8 names directly.
