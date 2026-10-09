"""
Opt-in compatibility for code written against OCP 7.x.

OCP 8 (OCCT 8) renamed or dropped a number of names that older scripts use
directly. :func:`enable` puts the old names back, on top of the OCP 8 bindings,
so such scripts keep running unchanged::

    from cadquery import occ_compat

    occ_compat.enable()

Nothing happens on import: the old names appear only after :func:`enable` is
called. It is idempotent and thread-safe, and it only sets attributes on OCP
modules and classes. It never replaces or changes a name that OCP 8 already
defines; the one exception is ``Bnd_Box.Get``/``Bnd_Box2d.Get``, whose OCP 8
binding cannot return at all (see :func:`_restore_bnd_get`).

What is restored:

* ``_s`` static-method names. OCP 7 bound every static C++ method as
  ``Foo_s``; OCP 8 binds OCCT 8 namespace functions (``TopoDS.Face`` and the
  other ``TopoDS`` casts) without the suffix. Every static method or namespace
  function ``Foo`` that has no ``Foo_s`` gets ``Foo_s`` as the very same
  callable. The list is computed from the bindings, not written by hand.
* Enum values nested in classes. OCP 7 exported them into the class scope
  (``AIS_PointCloud.DM_Points``); OCP 8 only has them on the enum type.
* Package collection typedefs (``TopTools_ListOfShape``, ``TColStd_Array1OfReal``,
  ``TColgp_Array1OfPnt``, ``TDF_LabelSequence`` ...), which OCP 8 binds once
  in ``OCP.collections`` under template names (``List_TopoDS_Shape``,
  ``Array1_double`` ...). The old name becomes an alias of that class in its old
  module. The table below comes from OCCT 8's own deprecated typedef headers
  (falling back to OCCT 7.9's), and every entry was checked against the
  bindings; it also holds the classes OCCT 8 renamed (``GCE2d_*`` ->
  ``GC_*2d``, ``Geom2dLProp_*`` -> ``GeomLProp_*``).
* ``Bnd_Box.Get()`` and ``Bnd_Box2d.Get()``, which return a tuple in the old
  order (``xmin, ymin, zmin, xmax, ymax, zmax``) that also carries the OCCT 8
  ``Limits`` field names (``Xmin``, ``Xmax`` ...).
* ``BRepTopAdaptor_FClass2d``, which OCP 8 no longer binds, as a Python class
  with the same constructor and ``Perform``/``PerformInfinitePoint``/
  ``TestOnRestriction`` methods, following OCCT's own algorithm on current
  OCCT classes.
"""

import math
import sys
import threading
from typing import Dict, Tuple

__all__ = ["enable", "enabled", "restored", "calls"]

_lock = threading.Lock()
_enabled = False
# "owner.name" -> kind, for every name enable() set ("static", "enum", "renamed",
# "moved", "patched", "class"). Filled once, under _lock.
_restored: Dict[str, str] = {}
# How often the replaced methods ("patched" in restored()) were called, by name.
_calls: Dict[str, int] = {}

# Old name -> new name, per old module. A bare new name lives in OCP.collections;
# "Module.Class" names a class elsewhere. Generated from the OCCT 8.0.1 deprecated typedef
# headers (src/Deprecated/NCollectionAliases), OCCT 7.9.3 typedefs where OCCT 8 dropped
# one, and OCP 7.9 vs 8.0 binding signatures; each target was checked to exist in OCP 8.
_RENAMED = {
    "AIS": {
        "AIS_ListOfInteractive": "List_AIS_InteractiveObject",
        "AIS_ManipulatorObjectSequence": "HSequence_AIS_InteractiveObject",
        "AIS_NArray1OfEntityOwner": "Array1_SelectMgr_EntityOwner",
        "AIS_NListOfEntityOwner": "List_SelectMgr_EntityOwner",
    },
    "AppParCurves": {
        "AppParCurves_Array1OfConstraintCouple": "Array1_AppParCurves_ConstraintCouple",
        "AppParCurves_HArray1OfConstraintCouple": "HArray1_AppParCurves_ConstraintCouple",
        "AppParCurves_SequenceOfMultiCurve": "Sequence_AppParCurves_MultiCurve",
    },
    "Aspect": {
        "Aspect_SequenceOfColor": "Sequence_Quantity_Color",
        "Aspect_TouchMap": "IndexedDataMap_size_t_Aspect_Touch",
        "Aspect_TrackedDevicePoseArray": "Array1_Aspect_TrackedDevicePose",
    },
    "BOPAlgo": {"BOPAlgo_ListOfCheckResult": "List_BOPAlgo_CheckResult",},
    "BOPDS": {
        "BOPDS_IndexedDataMapOfPaveBlockListOfInteger": "IndexedDataMap_BOPDS_PaveBlock_List_int",
        "BOPDS_IndexedDataMapOfPaveBlockListOfPaveBlock": "IndexedDataMap_BOPDS_PaveBlock_List_BOPDS_PaveBlock",
        "BOPDS_IndexedMapOfPaveBlock": "IndexedMap_BOPDS_PaveBlock",
        "BOPDS_ListOfPave": "List_BOPDS_Pave",
        "BOPDS_ListOfPaveBlock": "List_BOPDS_PaveBlock",
        "BOPDS_MapOfPair": "Map_BOPDS_Pair",
        "BOPDS_MapOfPaveBlock": "Map_BOPDS_PaveBlock",
        "BOPDS_VectorOfCurve": "DynamicArray_BOPDS_Curve",
        "BOPDS_VectorOfFaceInfo": "DynamicArray_BOPDS_FaceInfo",
        "BOPDS_VectorOfInterfEE": "DynamicArray_BOPDS_InterfEE",
        "BOPDS_VectorOfInterfEF": "DynamicArray_BOPDS_InterfEF",
        "BOPDS_VectorOfInterfEZ": "DynamicArray_BOPDS_InterfEZ",
        "BOPDS_VectorOfInterfFF": "DynamicArray_BOPDS_InterfFF",
        "BOPDS_VectorOfInterfFZ": "DynamicArray_BOPDS_InterfFZ",
        "BOPDS_VectorOfInterfVE": "DynamicArray_BOPDS_InterfVE",
        "BOPDS_VectorOfInterfVF": "DynamicArray_BOPDS_InterfVF",
        "BOPDS_VectorOfInterfVV": "DynamicArray_BOPDS_InterfVV",
        "BOPDS_VectorOfInterfVZ": "DynamicArray_BOPDS_InterfVZ",
        "BOPDS_VectorOfInterfZZ": "DynamicArray_BOPDS_InterfZZ",
        "BOPDS_VectorOfListOfPaveBlock": "DynamicArray_List_BOPDS_PaveBlock",
        "BOPDS_VectorOfPoint": "DynamicArray_BOPDS_Point",
    },
    "BOPTools": {
        "BOPTools_ListOfConnexityBlock": "List_BOPTools_ConnexityBlock",
        "BOPTools_ListOfCoupleOfShape": "List_BOPTools_CoupleOfShape",
    },
    "BRep": {
        "BRep_ListOfCurveRepresentation": "List_BRep_CurveRepresentation",
        "BRep_ListOfPointRepresentation": "List_BRep_PointRepresentation",
    },
    "BRepExtrema": {
        "BRepExtrema_SeqOfSolution": "Sequence_BRepExtrema_SolutionElem",
        "BRepExtrema_ShapeList": "DynamicArray_TopoDS_Shape",
    },
    "BRepOffset": {
        "BRepOffset_DataMapOfShapeOffset": "DataMap_TopoDS_Shape_BRepOffset_Offset_TopTools_ShapeMapHasher",
        "BRepOffset_ListOfInterval": "List_BRepOffset_Interval",
    },
    "BRepTopAdaptor": {
        "BRepTopAdaptor_MapOfShapeTool": "DataMap_TopoDS_Shape_BRepTopAdaptor_Tool_TopTools_ShapeMapHasher",
    },
    "Bnd": {
        "Bnd_Array1OfBox": "Array1_Bnd_Box",
        "Bnd_HArray1OfBox": "HArray1_Bnd_Box",
    },
    "ChFiDS": {
        "ChFiDS_HData": "HSequence_ChFiDS_SurfData",
        "ChFiDS_ListOfHElSpine": "List_ChFiDS_ElSpine",
        "ChFiDS_ListOfStripe": "List_ChFiDS_Stripe",
        "ChFiDS_Regularities": "List_ChFiDS_Regul",
        "ChFiDS_SecArray1": "Array1_ChFiDS_CircSection",
        "ChFiDS_SecHArray1": "HArray1_ChFiDS_CircSection",
        "ChFiDS_SequenceOfSurfData": "Sequence_ChFiDS_SurfData",
    },
    "Expr": {"Expr_Array1OfNamedUnknown": "Array1_Expr_NamedUnknown",},
    "ExprIntrp": {
        "ExprIntrp_SequenceOfNamedExpression": "Sequence_Expr_NamedExpression",
        "ExprIntrp_SequenceOfNamedFunction": "Sequence_Expr_NamedFunction",
    },
    "Extrema": {
        "Extrema_SequenceOfPOnCurv": "Sequence_Extrema_POnCurv",
        "Extrema_SequenceOfPOnSurf": "Sequence_Extrema_POnSurf",
    },
    "Font": {"Font_NListOfSystemFont": "List_Font_SystemFont",},
    "GCE2d": {
        "GCE2d_MakeArcOfCircle": "GC.GC_MakeArcOfCircle2d",
        "GCE2d_MakeArcOfEllipse": "GC.GC_MakeArcOfEllipse2d",
        "GCE2d_MakeArcOfHyperbola": "GC.GC_MakeArcOfHyperbola2d",
        "GCE2d_MakeArcOfParabola": "GC.GC_MakeArcOfParabola2d",
        "GCE2d_MakeCircle": "GC.GC_MakeCircle2d",
        "GCE2d_MakeEllipse": "GC.GC_MakeEllipse2d",
        "GCE2d_MakeHyperbola": "GC.GC_MakeHyperbola2d",
        "GCE2d_MakeLine": "GC.GC_MakeLine2d",
        "GCE2d_MakeMirror": "GC.GC_MakeMirror2d",
        "GCE2d_MakeParabola": "GC.GC_MakeParabola2d",
        "GCE2d_MakeRotation": "GC.GC_MakeRotation2d",
        "GCE2d_MakeScale": "GC.GC_MakeScale2d",
        "GCE2d_MakeSegment": "GC.GC_MakeSegment2d",
        "GCE2d_MakeTranslation": "GC.GC_MakeTranslation2d",
        "GCE2d_Root": "GC.GC_Root",
    },
    "Geom2dLProp": {
        "Geom2dLProp_CLProps2d": "GeomLProp.GeomLProp_CLProps2d",
        "Geom2dLProp_CurAndInf2d": "GeomLProp.GeomLProp_CurAndInf2d",
    },
    "GeomInt": {"GeomInt_VectorOfReal": "DynamicArray_double",},
    "GeomPlate": {"GeomPlate_SequenceOfAij": "Sequence_GeomPlate_Aij",},
    "Graphic3d": {
        "Graphic3d_Array1OfAttribute": "Array1_Graphic3d_Attribute",
        "Graphic3d_GraphicDriverFactoryList": "List_Graphic3d_GraphicDriverFactory",
        "Graphic3d_Mat4": "Mat4_float",
        "Graphic3d_Mat4d": "Mat4_double",
        "Graphic3d_SequenceOfGroup": "Sequence_Graphic3d_Group",
        "Graphic3d_ShaderAttributeList": "Sequence_Graphic3d_ShaderAttribute",
        "Graphic3d_ShaderObjectList": "Sequence_Graphic3d_ShaderObject",
        "Graphic3d_ShaderVariableList": "Sequence_Graphic3d_ShaderVariable",
        "Graphic3d_Vec2d": "Vec2_double",
        "Graphic3d_Vec2i": "Vec2_int",
        "Graphic3d_Vec3i": "Vec3_int",
        "Graphic3d_Vec4": "Vec4_float",
        "Graphic3d_Vec4d": "Vec4_double",
        "Graphic3d_Vec4i": "Vec4_int",
        "Graphic3d_Vec4ub": "Vec4_uint8_t",
    },
    "HLRAlgo": {
        "HLRAlgo_Array1OfPHDat": "Array1_HLRAlgo_PolyHidingData",
        "HLRAlgo_Array1OfPINod": "Array1_HLRAlgo_PolyInternalNode",
        "HLRAlgo_Array1OfPISeg": "Array1_HLRAlgo_PolyInternalSegment",
        "HLRAlgo_Array1OfTData": "Array1_HLRAlgo_TriangleData",
        "HLRAlgo_HArray1OfPHDat": "HArray1_HLRAlgo_PolyHidingData",
        "HLRAlgo_HArray1OfTData": "HArray1_HLRAlgo_TriangleData",
        "HLRAlgo_InterferenceList": "List_HLRAlgo_Interference",
        "HLRAlgo_ListOfBPoint": "List_HLRAlgo_BiPoint",
    },
    "HLRBRep": {
        "HLRBRep_Array1OfEData": "Array1_HLRBRep_EdgeData",
        "HLRBRep_Array1OfFData": "Array1_HLRBRep_FaceData",
        "HLRBRep_SeqOfShapeBounds": "Sequence_HLRBRep_ShapeBounds",
    },
    "IFSelect": {"IFSelect_TSeqOfSelection": "Sequence_IFSelect_Selection",},
    "IGESAppli": {
        "IGESAppli_Array1OfFiniteElement": "Array1_IGESAppli_FiniteElement",
        "IGESAppli_Array1OfNode": "Array1_IGESAppli_Node",
        "IGESAppli_HArray1OfFiniteElement": "HArray1_IGESAppli_FiniteElement",
        "IGESAppli_HArray1OfNode": "HArray1_IGESAppli_Node",
    },
    "IGESBasic": {
        "IGESBasic_Array1OfLineFontEntity": "Array1_IGESData_LineFontEntity",
        "IGESBasic_HArray1OfLineFontEntity": "HArray1_IGESData_LineFontEntity",
        "IGESBasic_HArray2OfHArray1OfReal": "HArray2_NCollection_HArray1",
    },
    "IGESData": {
        "IGESData_Array1OfIGESEntity": "Array1_IGESData_IGESEntity",
        "IGESData_HArray1OfIGESEntity": "HArray1_IGESData_IGESEntity",
    },
    "IGESDefs": {
        "IGESDefs_Array1OfTabularData": "Array1_IGESDefs_TabularData",
        "IGESDefs_HArray1OfTabularData": "HArray1_IGESDefs_TabularData",
    },
    "IGESDimen": {
        "IGESDimen_Array1OfGeneralNote": "Array1_IGESDimen_GeneralNote",
        "IGESDimen_Array1OfLeaderArrow": "Array1_IGESDimen_LeaderArrow",
        "IGESDimen_HArray1OfGeneralNote": "HArray1_IGESDimen_GeneralNote",
        "IGESDimen_HArray1OfLeaderArrow": "HArray1_IGESDimen_LeaderArrow",
    },
    "IGESDraw": {
        "IGESDraw_Array1OfConnectPoint": "Array1_IGESDraw_ConnectPoint",
        "IGESDraw_Array1OfViewKindEntity": "Array1_IGESData_ViewKindEntity",
        "IGESDraw_HArray1OfConnectPoint": "HArray1_IGESDraw_ConnectPoint",
        "IGESDraw_HArray1OfViewKindEntity": "HArray1_IGESData_ViewKindEntity",
    },
    "IGESGeom": {
        "IGESGeom_Array1OfBoundary": "Array1_IGESGeom_Boundary",
        "IGESGeom_Array1OfCurveOnSurface": "Array1_IGESGeom_CurveOnSurface",
        "IGESGeom_Array1OfTransformationMatrix": "Array1_IGESGeom_TransformationMatrix",
        "IGESGeom_HArray1OfBoundary": "HArray1_IGESGeom_Boundary",
        "IGESGeom_HArray1OfCurveOnSurface": "HArray1_IGESGeom_CurveOnSurface",
        "IGESGeom_HArray1OfTransformationMatrix": "HArray1_IGESGeom_TransformationMatrix",
    },
    "IGESGraph": {
        "IGESGraph_Array1OfColor": "Array1_IGESGraph_Color",
        "IGESGraph_Array1OfTextDisplayTemplate": "Array1_IGESGraph_TextDisplayTemplate",
        "IGESGraph_Array1OfTextFontDef": "Array1_IGESGraph_TextFontDef",
        "IGESGraph_HArray1OfColor": "HArray1_IGESGraph_Color",
        "IGESGraph_HArray1OfTextDisplayTemplate": "HArray1_IGESGraph_TextDisplayTemplate",
        "IGESGraph_HArray1OfTextFontDef": "HArray1_IGESGraph_TextFontDef",
    },
    "IGESSolid": {
        "IGESSolid_Array1OfFace": "Array1_IGESSolid_Face",
        "IGESSolid_Array1OfLoop": "Array1_IGESSolid_Loop",
        "IGESSolid_Array1OfShell": "Array1_IGESSolid_Shell",
        "IGESSolid_Array1OfVertexList": "Array1_IGESSolid_VertexList",
        "IGESSolid_HArray1OfFace": "HArray1_IGESSolid_Face",
        "IGESSolid_HArray1OfLoop": "HArray1_IGESSolid_Loop",
        "IGESSolid_HArray1OfShell": "HArray1_IGESSolid_Shell",
        "IGESSolid_HArray1OfVertexList": "HArray1_IGESSolid_VertexList",
    },
    "IVtk": {
        "IVtk_IdTypeMap": "Map_IVtk_IdType",
        "IVtk_SelectionModeList": "List_IVtk_SelectionMode",
        "IVtk_ShapeIdList": "List_IVtk_IdType",
    },
    "IntPatch": {
        "IntPatch_SequenceOfLine": "Sequence_IntPatch_Line",
        "IntPatch_SequenceOfPoint": "Sequence_IntPatch_Point",
    },
    "IntPolyh": {"IntPolyh_ListOfCouples": "List_IntPolyh_Couple",},
    "IntRes2d": {
        "IntRes2d_SequenceOfIntersectionPoint": "Sequence_IntRes2d_IntersectionPoint",
    },
    "IntSurf": {
        "IntSurf_ListOfPntOn2S": "List_IntSurf_PntOn2S",
        "IntSurf_SequenceOfInteriorPoint": "Sequence_IntSurf_InteriorPoint",
        "IntSurf_SequenceOfPathPoint": "Sequence_IntSurf_PathPoint",
    },
    "IntTools": {
        "IntTools_ListOfCurveRangeSample": "List_IntTools_CurveRangeSample",
        "IntTools_ListOfSurfaceRangeSample": "List_IntTools_SurfaceRangeSample",
        "IntTools_SequenceOfCommonPrts": "Sequence_IntTools_CommonPrt",
        "IntTools_SequenceOfCurves": "Sequence_IntTools_Curve",
        "IntTools_SequenceOfPntOn2Faces": "Sequence_IntTools_PntOn2Faces",
        "IntTools_SequenceOfRanges": "Sequence_IntTools_Range",
        "IntTools_SequenceOfRoots": "Sequence_IntTools_Root",
    },
    "Interface": {
        "Interface_Array1OfHAsciiString": "Array1_TCollection_HAsciiString",
        "Interface_HArray1OfHAsciiString": "HArray1_TCollection_HAsciiString",
        "Interface_IndexedMapOfAsciiString": "IndexedMap_TCollection_AsciiString",
    },
    "Intf": {"Intf_Array1OfLin": "Array1_gp_Lin",},
    "Law": {"Law_Laws": "List_Law_Function",},
    "LocOpe": {
        "LocOpe_SequenceOfCirc": "Sequence_gp_Circ",
        "LocOpe_SequenceOfLin": "Sequence_gp_Lin",
    },
    "MAT": {
        "MAT_SequenceOfArc": "Sequence_MAT_Arc",
        "MAT_SequenceOfBasicElt": "Sequence_MAT_BasicElt",
    },
    "MAT2d": {
        "MAT2d_SequenceOfConnexion": "Sequence_MAT2d_Connexion",
        "MAT2d_SequenceOfSequenceOfGeometry": "Sequence_Sequence_Geom2d_Geometry",
    },
    "MeshVS": {
        "MeshVS_Array1OfSequenceOfInteger": "Array1_Sequence_int",
        "MeshVS_DataMapOfIntegerAsciiString": "DataMap_int_TCollection_AsciiString",
        "MeshVS_DataMapOfIntegerColor": "DataMap_int_Quantity_Color",
        "MeshVS_DataMapOfIntegerTwoColors": "DataMap_int_MeshVS_TwoColors",
        "MeshVS_DataMapOfIntegerVector": "DataMap_int_gp_Vec",
        "MeshVS_HArray1OfSequenceOfInteger": "HArray1_Sequence_int",
    },
    "Message": {
        "Message_ListOfAlert": "List_Message_Alert",
        "Message_SequenceOfPrinters": "Sequence_Message_Printer",
    },
    "OpenGl": {
        "OpenGl_ColorFormats": "DynamicArray_int",
        "OpenGl_ShaderProgramList": "Sequence_OpenGl_ShaderProgram",
    },
    "PCDM": {
        "PCDM_SequenceOfDocument": "Sequence_PCDM_Document",
        "PCDM_SequenceOfReference": "Sequence_PCDM_Reference",
    },
    "Plate": {"Plate_Array1OfPinpointConstraint": "Array1_Plate_PinpointConstraint",},
    "Poly": {
        "Poly_Array1OfTriangle": "Array1_Poly_Triangle",
        "Poly_HArray1OfTriangle": "HArray1_Poly_Triangle",
        "Poly_ListOfTriangulation": "List_Poly_Triangulation",
    },
    "Prs3d": {"Prs3d_NListOfSequenceOfPnt": "List_NCollection_HSequence",},
    "PrsMgr": {
        "PrsMgr_ListOfPresentableObjects": "List_PrsMgr_PresentableObject",
        "PrsMgr_Presentations": "Sequence_PrsMgr_Presentation",
    },
    "Quantity": {
        "Quantity_Array1OfColor": "Array1_Quantity_Color",
        "Quantity_HArray1OfColor": "HArray1_Quantity_Color",
    },
    "RWMesh": {
        "RWMesh_NodeAttributeMap": "DataMap_TopoDS_Shape_RWMesh_NodeAttributes_TopTools_ShapeMapHasher",
    },
    "Resource": {
        "Resource_DataMapOfAsciiStringAsciiString": "DataMap_TCollection_AsciiString_TCollection_AsciiString",
    },
    "STEPSelections": {
        "STEPSelections_HSequenceOfAssemblyLink": "HSequence_STEPSelections_AssemblyLink",
        "STEPSelections_SequenceOfAssemblyLink": "Sequence_STEPSelections_AssemblyLink",
    },
    "Select3D": {"Select3D_EntitySequence": "Sequence_Select3D_SensitiveEntity",},
    "SelectMgr": {
        "SelectMgr_ListOfFilter": "List_SelectMgr_Filter",
        "SelectMgr_MapOfOwners": "DataMap_SelectMgr_EntityOwner_int",
        "SelectMgr_SequenceOfOwner": "Sequence_SelectMgr_EntityOwner",
        "SelectMgr_SequenceOfSelection": "Sequence_SelectMgr_Selection",
        "SelectMgr_Vec3": "Vec3_double",
    },
    "ShapeAnalysis": {
        "ShapeAnalysis_BoxBndTree": "UBTree_int_Bnd_Box",
        "ShapeAnalysis_DataMapOfShapeListOfReal": "DataMap_TopoDS_Shape_List_double_TopTools_ShapeMapHasher",
        "ShapeAnalysis_HSequenceOfFreeBounds": "HSequence_ShapeAnalysis_FreeBoundData",
        "ShapeAnalysis_SequenceOfFreeBounds": "Sequence_ShapeAnalysis_FreeBoundData",
    },
    "ShapeExtend": {
        "ShapeExtend_DataMapOfShapeListOfMsg": "DataMap_TopoDS_Shape_List_Message_Msg_TopTools_ShapeMapHasher",
        "ShapeExtend_DataMapOfTransientListOfMsg": "DataMap_Standard_Transient_List_Message_Msg",
    },
    "ShapeFix": {"ShapeFix_SequenceOfWireSegment": "Sequence_ShapeFix_WireSegment",},
    "StdStorage": {
        "StdStorage_HSequenceOfRoots": "HSequence_StdStorage_Root",
        "StdStorage_SequenceOfRoots": "Sequence_StdStorage_Root",
    },
    "StepAP203": {
        "StepAP203_Array1OfApprovedItem": "Array1_StepAP203_ApprovedItem",
        "StepAP203_Array1OfCertifiedItem": "Array1_StepAP203_CertifiedItem",
        "StepAP203_Array1OfChangeRequestItem": "Array1_StepAP203_ChangeRequestItem",
        "StepAP203_Array1OfClassifiedItem": "Array1_StepAP203_ClassifiedItem",
        "StepAP203_Array1OfContractedItem": "Array1_StepAP203_ContractedItem",
        "StepAP203_Array1OfDateTimeItem": "Array1_StepAP203_DateTimeItem",
        "StepAP203_Array1OfPersonOrganizationItem": "Array1_StepAP203_PersonOrganizationItem",
        "StepAP203_Array1OfSpecifiedItem": "Array1_StepAP203_SpecifiedItem",
        "StepAP203_Array1OfStartRequestItem": "Array1_StepAP203_StartRequestItem",
        "StepAP203_Array1OfWorkItem": "Array1_StepAP203_WorkItem",
        "StepAP203_HArray1OfApprovedItem": "HArray1_StepAP203_ApprovedItem",
        "StepAP203_HArray1OfCertifiedItem": "HArray1_StepAP203_CertifiedItem",
        "StepAP203_HArray1OfChangeRequestItem": "HArray1_StepAP203_ChangeRequestItem",
        "StepAP203_HArray1OfClassifiedItem": "HArray1_StepAP203_ClassifiedItem",
        "StepAP203_HArray1OfContractedItem": "HArray1_StepAP203_ContractedItem",
        "StepAP203_HArray1OfDateTimeItem": "HArray1_StepAP203_DateTimeItem",
        "StepAP203_HArray1OfPersonOrganizationItem": "HArray1_StepAP203_PersonOrganizationItem",
        "StepAP203_HArray1OfSpecifiedItem": "HArray1_StepAP203_SpecifiedItem",
        "StepAP203_HArray1OfStartRequestItem": "HArray1_StepAP203_StartRequestItem",
        "StepAP203_HArray1OfWorkItem": "HArray1_StepAP203_WorkItem",
    },
    "StepAP214": {
        "StepAP214_Array1OfApprovalItem": "Array1_StepAP214_ApprovalItem",
        "StepAP214_Array1OfAutoDesignDateAndPersonItem": "Array1_StepAP214_AutoDesignDateAndPersonItem",
        "StepAP214_Array1OfAutoDesignDateAndTimeItem": "Array1_StepAP214_AutoDesignDateAndTimeItem",
        "StepAP214_Array1OfAutoDesignDatedItem": "Array1_StepAP214_AutoDesignDatedItem",
        "StepAP214_Array1OfAutoDesignGeneralOrgItem": "Array1_StepAP214_AutoDesignGeneralOrgItem",
        "StepAP214_Array1OfAutoDesignGroupedItem": "Array1_StepAP214_AutoDesignGroupedItem",
        "StepAP214_Array1OfAutoDesignPresentedItemSelect": "Array1_StepAP214_AutoDesignPresentedItemSelect",
        "StepAP214_Array1OfAutoDesignReferencingItem": "Array1_StepAP214_AutoDesignReferencingItem",
        "StepAP214_Array1OfDateAndTimeItem": "Array1_StepAP214_DateAndTimeItem",
        "StepAP214_Array1OfDateItem": "Array1_StepAP214_DateItem",
        "StepAP214_Array1OfDocumentReferenceItem": "Array1_StepAP214_DocumentReferenceItem",
        "StepAP214_Array1OfExternalIdentificationItem": "Array1_StepAP214_ExternalIdentificationItem",
        "StepAP214_Array1OfGroupItem": "Array1_StepAP214_GroupItem",
        "StepAP214_Array1OfOrganizationItem": "Array1_StepAP214_OrganizationItem",
        "StepAP214_Array1OfPersonAndOrganizationItem": "Array1_StepAP214_PersonAndOrganizationItem",
        "StepAP214_Array1OfPresentedItemSelect": "Array1_StepAP214_PresentedItemSelect",
        "StepAP214_Array1OfSecurityClassificationItem": "Array1_StepAP214_SecurityClassificationItem",
        "StepAP214_HArray1OfApprovalItem": "HArray1_StepAP214_ApprovalItem",
        "StepAP214_HArray1OfAutoDesignDateAndPersonItem": "HArray1_StepAP214_AutoDesignDateAndPersonItem",
        "StepAP214_HArray1OfAutoDesignDateAndTimeItem": "HArray1_StepAP214_AutoDesignDateAndTimeItem",
        "StepAP214_HArray1OfAutoDesignDatedItem": "HArray1_StepAP214_AutoDesignDatedItem",
        "StepAP214_HArray1OfAutoDesignGeneralOrgItem": "HArray1_StepAP214_AutoDesignGeneralOrgItem",
        "StepAP214_HArray1OfAutoDesignGroupedItem": "HArray1_StepAP214_AutoDesignGroupedItem",
        "StepAP214_HArray1OfAutoDesignPresentedItemSelect": "HArray1_StepAP214_AutoDesignPresentedItemSelect",
        "StepAP214_HArray1OfAutoDesignReferencingItem": "HArray1_StepAP214_AutoDesignReferencingItem",
        "StepAP214_HArray1OfDateAndTimeItem": "HArray1_StepAP214_DateAndTimeItem",
        "StepAP214_HArray1OfDateItem": "HArray1_StepAP214_DateItem",
        "StepAP214_HArray1OfDocumentReferenceItem": "HArray1_StepAP214_DocumentReferenceItem",
        "StepAP214_HArray1OfExternalIdentificationItem": "HArray1_StepAP214_ExternalIdentificationItem",
        "StepAP214_HArray1OfGroupItem": "HArray1_StepAP214_GroupItem",
        "StepAP214_HArray1OfOrganizationItem": "HArray1_StepAP214_OrganizationItem",
        "StepAP214_HArray1OfPersonAndOrganizationItem": "HArray1_StepAP214_PersonAndOrganizationItem",
        "StepAP214_HArray1OfPresentedItemSelect": "HArray1_StepAP214_PresentedItemSelect",
        "StepAP214_HArray1OfSecurityClassificationItem": "HArray1_StepAP214_SecurityClassificationItem",
    },
    "StepBasic": {
        "StepBasic_Array1OfApproval": "Array1_StepBasic_Approval",
        "StepBasic_Array1OfDerivedUnitElement": "Array1_StepBasic_DerivedUnitElement",
        "StepBasic_Array1OfDocument": "Array1_StepBasic_Document",
        "StepBasic_Array1OfNamedUnit": "Array1_StepBasic_NamedUnit",
        "StepBasic_Array1OfOrganization": "Array1_StepBasic_Organization",
        "StepBasic_Array1OfPerson": "Array1_StepBasic_Person",
        "StepBasic_Array1OfProduct": "Array1_StepBasic_Product",
        "StepBasic_Array1OfProductContext": "Array1_StepBasic_ProductContext",
        "StepBasic_Array1OfUncertaintyMeasureWithUnit": "Array1_StepBasic_UncertaintyMeasureWithUnit",
        "StepBasic_HArray1OfApproval": "HArray1_StepBasic_Approval",
        "StepBasic_HArray1OfDerivedUnitElement": "HArray1_StepBasic_DerivedUnitElement",
        "StepBasic_HArray1OfDocument": "HArray1_StepBasic_Document",
        "StepBasic_HArray1OfNamedUnit": "HArray1_StepBasic_NamedUnit",
        "StepBasic_HArray1OfOrganization": "HArray1_StepBasic_Organization",
        "StepBasic_HArray1OfPerson": "HArray1_StepBasic_Person",
        "StepBasic_HArray1OfProduct": "HArray1_StepBasic_Product",
        "StepBasic_HArray1OfProductContext": "HArray1_StepBasic_ProductContext",
        "StepBasic_HArray1OfUncertaintyMeasureWithUnit": "HArray1_StepBasic_UncertaintyMeasureWithUnit",
    },
    "StepDimTol": {
        "StepDimTol_Array1OfDatumReference": "Array1_StepDimTol_DatumReference",
        "StepDimTol_Array1OfDatumReferenceCompartment": "Array1_StepDimTol_DatumReferenceCompartment",
        "StepDimTol_Array1OfDatumReferenceElement": "Array1_StepDimTol_DatumReferenceElement",
        "StepDimTol_Array1OfDatumReferenceModifier": "Array1_StepDimTol_DatumReferenceModifier",
        "StepDimTol_Array1OfDatumSystemOrReference": "Array1_StepDimTol_DatumSystemOrReference",
        "StepDimTol_Array1OfGeometricToleranceModifier": "Array1_StepDimTol_GeometricToleranceModifier",
        "StepDimTol_Array1OfToleranceZoneTarget": "Array1_StepDimTol_ToleranceZoneTarget",
        "StepDimTol_HArray1OfDatumReference": "HArray1_StepDimTol_DatumReference",
        "StepDimTol_HArray1OfDatumReferenceCompartment": "HArray1_StepDimTol_DatumReferenceCompartment",
        "StepDimTol_HArray1OfDatumReferenceElement": "HArray1_StepDimTol_DatumReferenceElement",
        "StepDimTol_HArray1OfDatumReferenceModifier": "HArray1_StepDimTol_DatumReferenceModifier",
        "StepDimTol_HArray1OfDatumSystemOrReference": "HArray1_StepDimTol_DatumSystemOrReference",
        "StepDimTol_HArray1OfToleranceZoneTarget": "HArray1_StepDimTol_ToleranceZoneTarget",
    },
    "StepElement": {
        "StepElement_Array1OfCurveElementEndReleasePacket": "Array1_StepElement_CurveElementEndReleasePacket",
        "StepElement_Array1OfCurveElementSectionDefinition": "Array1_StepElement_CurveElementSectionDefinition",
        "StepElement_Array1OfMeasureOrUnspecifiedValue": "Array1_StepElement_MeasureOrUnspecifiedValue",
        "StepElement_Array1OfSurfaceSection": "Array1_StepElement_SurfaceSection",
        "StepElement_Array1OfVolumeElementPurposeMember": "Array1_StepElement_VolumeElementPurposeMember",
        "StepElement_HArray1OfCurveElementEndReleasePacket": "HArray1_StepElement_CurveElementEndReleasePacket",
        "StepElement_HArray1OfCurveElementSectionDefinition": "HArray1_StepElement_CurveElementSectionDefinition",
        "StepElement_HArray1OfHSequenceOfSurfaceElementPurposeMember": "HArray1_NCollection_HSequence",
        "StepElement_HArray1OfMeasureOrUnspecifiedValue": "HArray1_StepElement_MeasureOrUnspecifiedValue",
        "StepElement_HArray1OfSurfaceSection": "HArray1_StepElement_SurfaceSection",
        "StepElement_HArray1OfVolumeElementPurposeMember": "HArray1_StepElement_VolumeElementPurposeMember",
        "StepElement_HSequenceOfCurveElementSectionDefinition": "HSequence_StepElement_CurveElementSectionDefinition",
        "StepElement_HSequenceOfElementMaterial": "HSequence_StepElement_ElementMaterial",
        "StepElement_SequenceOfCurveElementSectionDefinition": "Sequence_StepElement_CurveElementSectionDefinition",
        "StepElement_SequenceOfElementMaterial": "Sequence_StepElement_ElementMaterial",
    },
    "StepFEA": {
        "StepFEA_Array1OfCurveElementEndOffset": "Array1_StepFEA_CurveElementEndOffset",
        "StepFEA_Array1OfCurveElementEndRelease": "Array1_StepFEA_CurveElementEndRelease",
        "StepFEA_Array1OfCurveElementInterval": "Array1_StepFEA_CurveElementInterval",
        "StepFEA_Array1OfDegreeOfFreedom": "Array1_StepFEA_DegreeOfFreedom",
        "StepFEA_Array1OfElementRepresentation": "Array1_StepFEA_ElementRepresentation",
        "StepFEA_Array1OfNodeRepresentation": "Array1_StepFEA_NodeRepresentation",
        "StepFEA_HArray1OfCurveElementEndOffset": "HArray1_StepFEA_CurveElementEndOffset",
        "StepFEA_HArray1OfCurveElementEndRelease": "HArray1_StepFEA_CurveElementEndRelease",
        "StepFEA_HArray1OfCurveElementInterval": "HArray1_StepFEA_CurveElementInterval",
        "StepFEA_HArray1OfDegreeOfFreedom": "HArray1_StepFEA_DegreeOfFreedom",
        "StepFEA_HArray1OfElementRepresentation": "HArray1_StepFEA_ElementRepresentation",
        "StepFEA_HArray1OfNodeRepresentation": "HArray1_StepFEA_NodeRepresentation",
        "StepFEA_HSequenceOfElementGeometricRelationship": "HSequence_StepFEA_ElementGeometricRelationship",
        "StepFEA_HSequenceOfElementRepresentation": "HSequence_StepFEA_ElementRepresentation",
        "StepFEA_SequenceOfElementGeometricRelationship": "Sequence_StepFEA_ElementGeometricRelationship",
        "StepFEA_SequenceOfElementRepresentation": "Sequence_StepFEA_ElementRepresentation",
    },
    "StepGeom": {
        "StepGeom_Array1OfCartesianPoint": "Array1_StepGeom_CartesianPoint",
        "StepGeom_Array1OfCompositeCurveSegment": "Array1_StepGeom_CompositeCurveSegment",
        "StepGeom_Array1OfPcurveOrSurface": "Array1_StepGeom_PcurveOrSurface",
        "StepGeom_Array1OfSurfaceBoundary": "Array1_StepGeom_SurfaceBoundary",
        "StepGeom_Array1OfTrimmingSelect": "Array1_StepGeom_TrimmingSelect",
        "StepGeom_Array2OfCartesianPoint": "Array2_StepGeom_CartesianPoint",
        "StepGeom_Array2OfSurfacePatch": "Array2_StepGeom_SurfacePatch",
        "StepGeom_HArray1OfCartesianPoint": "HArray1_StepGeom_CartesianPoint",
        "StepGeom_HArray1OfCompositeCurveSegment": "HArray1_StepGeom_CompositeCurveSegment",
        "StepGeom_HArray1OfPcurveOrSurface": "HArray1_StepGeom_PcurveOrSurface",
        "StepGeom_HArray1OfSurfaceBoundary": "HArray1_StepGeom_SurfaceBoundary",
        "StepGeom_HArray1OfTrimmingSelect": "HArray1_StepGeom_TrimmingSelect",
        "StepGeom_HArray2OfCartesianPoint": "HArray2_StepGeom_CartesianPoint",
        "StepGeom_HArray2OfSurfacePatch": "HArray2_StepGeom_SurfacePatch",
    },
    "StepRepr": {
        "StepRepr_Array1OfMaterialPropertyRepresentation": "Array1_StepRepr_MaterialPropertyRepresentation",
        "StepRepr_Array1OfPropertyDefinitionRepresentation": "Array1_StepRepr_PropertyDefinitionRepresentation",
        "StepRepr_Array1OfRepresentationItem": "Array1_StepRepr_RepresentationItem",
        "StepRepr_Array1OfShapeAspect": "Array1_StepRepr_ShapeAspect",
        "StepRepr_HArray1OfMaterialPropertyRepresentation": "HArray1_StepRepr_MaterialPropertyRepresentation",
        "StepRepr_HArray1OfPropertyDefinitionRepresentation": "HArray1_StepRepr_PropertyDefinitionRepresentation",
        "StepRepr_HArray1OfRepresentationItem": "HArray1_StepRepr_RepresentationItem",
        "StepRepr_HArray1OfShapeAspect": "HArray1_StepRepr_ShapeAspect",
    },
    "StepShape": {
        "StepShape_Array1OfConnectedEdgeSet": "Array1_StepShape_ConnectedEdgeSet",
        "StepShape_Array1OfConnectedFaceSet": "Array1_StepShape_ConnectedFaceSet",
        "StepShape_Array1OfEdge": "Array1_StepShape_Edge",
        "StepShape_Array1OfFace": "Array1_StepShape_Face",
        "StepShape_Array1OfFaceBound": "Array1_StepShape_FaceBound",
        "StepShape_Array1OfGeometricSetSelect": "Array1_StepShape_GeometricSetSelect",
        "StepShape_Array1OfOrientedClosedShell": "Array1_StepShape_OrientedClosedShell",
        "StepShape_Array1OfOrientedEdge": "Array1_StepShape_OrientedEdge",
        "StepShape_Array1OfShapeDimensionRepresentationItem": "Array1_StepShape_ShapeDimensionRepresentationItem",
        "StepShape_Array1OfShell": "Array1_StepShape_Shell",
        "StepShape_Array1OfValueQualifier": "Array1_StepShape_ValueQualifier",
        "StepShape_HArray1OfConnectedEdgeSet": "HArray1_StepShape_ConnectedEdgeSet",
        "StepShape_HArray1OfConnectedFaceSet": "HArray1_StepShape_ConnectedFaceSet",
        "StepShape_HArray1OfEdge": "HArray1_StepShape_Edge",
        "StepShape_HArray1OfFace": "HArray1_StepShape_Face",
        "StepShape_HArray1OfFaceBound": "HArray1_StepShape_FaceBound",
        "StepShape_HArray1OfGeometricSetSelect": "HArray1_StepShape_GeometricSetSelect",
        "StepShape_HArray1OfOrientedClosedShell": "HArray1_StepShape_OrientedClosedShell",
        "StepShape_HArray1OfOrientedEdge": "HArray1_StepShape_OrientedEdge",
        "StepShape_HArray1OfShapeDimensionRepresentationItem": "HArray1_StepShape_ShapeDimensionRepresentationItem",
        "StepShape_HArray1OfShell": "HArray1_StepShape_Shell",
        "StepShape_HArray1OfValueQualifier": "HArray1_StepShape_ValueQualifier",
    },
    "StepToTopoDS": {
        "StepToTopoDS_DataMapOfRI": "DataMap_StepRepr_RepresentationItem_TopoDS_Shape",
        "StepToTopoDS_DataMapOfRINames": "DataMap_TCollection_AsciiString_TopoDS_Shape",
        "StepToTopoDS_DataMapOfTRI": "DataMap_StepShape_TopologicalRepresentationItem_TopoDS_Shape",
    },
    "StepVisual": {
        "StepVisual_Array1OfAnnotationPlaneElement": "Array1_StepVisual_AnnotationPlaneElement",
        "StepVisual_Array1OfBoxCharacteristicSelect": "Array1_StepVisual_BoxCharacteristicSelect",
        "StepVisual_Array1OfCameraModelD3MultiClippingInterectionSelect": "Array1_StepVisual_CameraModelD3MultiClippingInterectionSelect",
        "StepVisual_Array1OfCameraModelD3MultiClippingUnionSelect": "Array1_StepVisual_CameraModelD3MultiClippingUnionSelect",
        "StepVisual_Array1OfCurveStyleFontPattern": "Array1_StepVisual_CurveStyleFontPattern",
        "StepVisual_Array1OfDirectionCountSelect": "Array1_StepVisual_DirectionCountSelect",
        "StepVisual_Array1OfDraughtingCalloutElement": "Array1_StepVisual_DraughtingCalloutElement",
        "StepVisual_Array1OfFillStyleSelect": "Array1_StepVisual_FillStyleSelect",
        "StepVisual_Array1OfInvisibleItem": "Array1_StepVisual_InvisibleItem",
        "StepVisual_Array1OfLayeredItem": "Array1_StepVisual_LayeredItem",
        "StepVisual_Array1OfPresentationStyleAssignment": "Array1_StepVisual_PresentationStyleAssignment",
        "StepVisual_Array1OfPresentationStyleSelect": "Array1_StepVisual_PresentationStyleSelect",
        "StepVisual_Array1OfRenderingPropertiesSelect": "Array1_StepVisual_RenderingPropertiesSelect",
        "StepVisual_Array1OfStyleContextSelect": "Array1_StepVisual_StyleContextSelect",
        "StepVisual_Array1OfSurfaceStyleElementSelect": "Array1_StepVisual_SurfaceStyleElementSelect",
        "StepVisual_Array1OfTessellatedEdgeOrVertex": "Array1_StepVisual_TessellatedEdgeOrVertex",
        "StepVisual_Array1OfTessellatedStructuredItem": "Array1_StepVisual_TessellatedStructuredItem",
        "StepVisual_Array1OfTextOrCharacter": "Array1_StepVisual_TextOrCharacter",
        "StepVisual_HArray1OfAnnotationPlaneElement": "HArray1_StepVisual_AnnotationPlaneElement",
        "StepVisual_HArray1OfBoxCharacteristicSelect": "HArray1_StepVisual_BoxCharacteristicSelect",
        "StepVisual_HArray1OfCameraModelD3MultiClippingInterectionSelect": "HArray1_StepVisual_CameraModelD3MultiClippingInterectionSelect",
        "StepVisual_HArray1OfCameraModelD3MultiClippingUnionSelect": "HArray1_StepVisual_CameraModelD3MultiClippingUnionSelect",
        "StepVisual_HArray1OfCurveStyleFontPattern": "HArray1_StepVisual_CurveStyleFontPattern",
        "StepVisual_HArray1OfDirectionCountSelect": "HArray1_StepVisual_DirectionCountSelect",
        "StepVisual_HArray1OfDraughtingCalloutElement": "HArray1_StepVisual_DraughtingCalloutElement",
        "StepVisual_HArray1OfFillStyleSelect": "HArray1_StepVisual_FillStyleSelect",
        "StepVisual_HArray1OfInvisibleItem": "HArray1_StepVisual_InvisibleItem",
        "StepVisual_HArray1OfLayeredItem": "HArray1_StepVisual_LayeredItem",
        "StepVisual_HArray1OfPresentationStyleAssignment": "HArray1_StepVisual_PresentationStyleAssignment",
        "StepVisual_HArray1OfPresentationStyleSelect": "HArray1_StepVisual_PresentationStyleSelect",
        "StepVisual_HArray1OfRenderingPropertiesSelect": "HArray1_StepVisual_RenderingPropertiesSelect",
        "StepVisual_HArray1OfStyleContextSelect": "HArray1_StepVisual_StyleContextSelect",
        "StepVisual_HArray1OfSurfaceStyleElementSelect": "HArray1_StepVisual_SurfaceStyleElementSelect",
        "StepVisual_HArray1OfTessellatedEdgeOrVertex": "HArray1_StepVisual_TessellatedEdgeOrVertex",
        "StepVisual_HArray1OfTessellatedStructuredItem": "HArray1_StepVisual_TessellatedStructuredItem",
        "StepVisual_HArray1OfTextOrCharacter": "HArray1_StepVisual_TextOrCharacter",
    },
    "Storage": {
        "Storage_HPArray": "HArray1_Standard_Persistent",
        "Storage_HSeqOfRoot": "HSequence_Storage_Root",
        "Storage_PArray": "Array1_Standard_Persistent",
        "Storage_PType": "IndexedDataMap_TCollection_AsciiString_int",
        "Storage_SeqOfRoot": "Sequence_Storage_Root",
    },
    "TColGeom": {
        "TColGeom_Array1OfBSplineCurve": "Array1_Geom_BSplineCurve",
        "TColGeom_Array1OfBezierCurve": "Array1_Geom_BezierCurve",
        "TColGeom_Array1OfCurve": "Array1_Geom_Curve",
        "TColGeom_Array1OfSurface": "Array1_Geom_Surface",
        "TColGeom_Array2OfBezierSurface": "Array2_Geom_BezierSurface",
        "TColGeom_Array2OfSurface": "Array2_Geom_Surface",
        "TColGeom_HArray1OfBSplineCurve": "HArray1_Geom_BSplineCurve",
        "TColGeom_HArray1OfCurve": "HArray1_Geom_Curve",
        "TColGeom_HArray2OfSurface": "HArray2_Geom_Surface",
        "TColGeom_HSequenceOfBoundedCurve": "HSequence_Geom_BoundedCurve",
        "TColGeom_SequenceOfBoundedCurve": "Sequence_Geom_BoundedCurve",
        "TColGeom_SequenceOfCurve": "Sequence_Geom_Curve",
    },
    "TColGeom2d": {
        "TColGeom2d_Array1OfBSplineCurve": "Array1_Geom2d_BSplineCurve",
        "TColGeom2d_Array1OfBezierCurve": "Array1_Geom2d_BezierCurve",
        "TColGeom2d_Array1OfCurve": "Array1_Geom2d_Curve",
        "TColGeom2d_HArray1OfBSplineCurve": "HArray1_Geom2d_BSplineCurve",
        "TColGeom2d_HArray1OfCurve": "HArray1_Geom2d_Curve",
        "TColGeom2d_HSequenceOfBoundedCurve": "HSequence_Geom2d_BoundedCurve",
        "TColGeom2d_SequenceOfBoundedCurve": "Sequence_Geom2d_BoundedCurve",
        "TColGeom2d_SequenceOfCurve": "Sequence_Geom2d_Curve",
    },
    "TColStd": {
        "TColStd_Array1OfAsciiString": "Array1_TCollection_AsciiString",
        "TColStd_Array1OfBoolean": "Array1_bool",
        "TColStd_Array1OfByte": "Array1_uint8_t",
        "TColStd_Array1OfExtendedString": "Array1_TCollection_ExtendedString",
        "TColStd_Array1OfInteger": "Array1_int",
        "TColStd_Array1OfListOfInteger": "Array1_List_int",
        "TColStd_Array1OfReal": "Array1_double",
        "TColStd_Array1OfTransient": "Array1_Standard_Transient",
        "TColStd_Array2OfInteger": "Array2_int",
        "TColStd_Array2OfReal": "Array2_double",
        "TColStd_Array2OfTransient": "Array2_Standard_Transient",
        "TColStd_DataMapOfIntegerInteger": "DataMap_int_int",
        "TColStd_DataMapOfIntegerReal": "DataMap_int_double",
        "TColStd_DataMapOfStringInteger": "DataMap_TCollection_ExtendedString_int",
        "TColStd_HArray1OfAsciiString": "HArray1_TCollection_AsciiString",
        "TColStd_HArray1OfBoolean": "HArray1_bool",
        "TColStd_HArray1OfByte": "HArray1_uint8_t",
        "TColStd_HArray1OfExtendedString": "HArray1_TCollection_ExtendedString",
        "TColStd_HArray1OfInteger": "HArray1_int",
        "TColStd_HArray1OfListOfInteger": "HArray1_List_int",
        "TColStd_HArray1OfReal": "HArray1_double",
        "TColStd_HArray1OfTransient": "HArray1_Standard_Transient",
        "TColStd_HArray2OfInteger": "HArray2_int",
        "TColStd_HArray2OfReal": "HArray2_double",
        "TColStd_HArray2OfTransient": "HArray2_Standard_Transient",
        "TColStd_HSequenceOfAsciiString": "HSequence_TCollection_AsciiString",
        "TColStd_HSequenceOfExtendedString": "HSequence_TCollection_ExtendedString",
        "TColStd_HSequenceOfHAsciiString": "HSequence_TCollection_HAsciiString",
        "TColStd_HSequenceOfHExtendedString": "HSequence_TCollection_HExtendedString",
        "TColStd_HSequenceOfInteger": "HSequence_int",
        "TColStd_HSequenceOfReal": "HSequence_double",
        "TColStd_HSequenceOfTransient": "HSequence_Standard_Transient",
        "TColStd_IndexedDataMapOfStringString": "IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString",
        "TColStd_IndexedMapOfTransient": "IndexedMap_Standard_Transient",
        "TColStd_ListOfAsciiString": "List_TCollection_AsciiString",
        "TColStd_ListOfInteger": "List_int",
        "TColStd_ListOfReal": "List_double",
        "TColStd_MapOfAsciiString": "Map_TCollection_AsciiString",
        "TColStd_MapOfInteger": "Map_int",
        "TColStd_SequenceOfAsciiString": "Sequence_TCollection_AsciiString",
        "TColStd_SequenceOfBoolean": "Sequence_bool",
        "TColStd_SequenceOfExtendedString": "Sequence_TCollection_ExtendedString",
        "TColStd_SequenceOfHAsciiString": "Sequence_TCollection_HAsciiString",
        "TColStd_SequenceOfHExtendedString": "Sequence_TCollection_HExtendedString",
        "TColStd_SequenceOfInteger": "Sequence_int",
        "TColStd_SequenceOfReal": "Sequence_double",
        "TColStd_SequenceOfTransient": "Sequence_Standard_Transient",
    },
    "TColgp": {
        "TColgp_Array1OfDir": "Array1_gp_Dir",
        "TColgp_Array1OfPnt": "Array1_gp_Pnt",
        "TColgp_Array1OfPnt2d": "Array1_gp_Pnt2d",
        "TColgp_Array1OfVec": "Array1_gp_Vec",
        "TColgp_Array1OfVec2d": "Array1_gp_Vec2d",
        "TColgp_Array1OfXY": "Array1_gp_XY",
        "TColgp_Array1OfXYZ": "Array1_gp_XYZ",
        "TColgp_Array2OfPnt": "Array2_gp_Pnt",
        "TColgp_Array2OfPnt2d": "Array2_gp_Pnt2d",
        "TColgp_Array2OfVec": "Array2_gp_Vec",
        "TColgp_Array2OfXYZ": "Array2_gp_XYZ",
        "TColgp_HArray1OfDir": "HArray1_gp_Dir",
        "TColgp_HArray1OfPnt": "HArray1_gp_Pnt",
        "TColgp_HArray1OfPnt2d": "HArray1_gp_Pnt2d",
        "TColgp_HArray1OfVec": "HArray1_gp_Vec",
        "TColgp_HArray1OfVec2d": "HArray1_gp_Vec2d",
        "TColgp_HArray1OfXY": "HArray1_gp_XY",
        "TColgp_HArray1OfXYZ": "HArray1_gp_XYZ",
        "TColgp_HArray2OfPnt": "HArray2_gp_Pnt",
        "TColgp_HArray2OfPnt2d": "HArray2_gp_Pnt2d",
        "TColgp_HArray2OfXYZ": "HArray2_gp_XYZ",
        "TColgp_SequenceOfPnt": "Sequence_gp_Pnt",
        "TColgp_SequenceOfPnt2d": "Sequence_gp_Pnt2d",
        "TColgp_SequenceOfVec": "Sequence_gp_Vec",
        "TColgp_SequenceOfXY": "Sequence_gp_XY",
        "TColgp_SequenceOfXYZ": "Sequence_gp_XYZ",
    },
    "TDF": {
        "TDF_AttributeDeltaList": "List_TDF_AttributeDelta",
        "TDF_AttributeIndexedMap": "IndexedMap_TDF_Attribute",
        "TDF_AttributeList": "List_TDF_Attribute",
        "TDF_AttributeMap": "Map_TDF_Attribute",
        "TDF_AttributeSequence": "Sequence_TDF_Attribute",
        "TDF_DeltaList": "List_TDF_Delta",
        "TDF_IDList": "List_Standard_GUID",
        "TDF_LabelDataMap": "DataMap_TDF_Label_TDF_Label",
        "TDF_LabelIndexedMap": "IndexedMap_TDF_Label",
        "TDF_LabelIntegerMap": "DataMap_TDF_Label_int",
        "TDF_LabelList": "List_TDF_Label",
        "TDF_LabelMap": "Map_TDF_Label",
        "TDF_LabelSequence": "Sequence_TDF_Label",
    },
    "TDataStd": {
        "TDataStd_DataMapOfStringByte": "DataMap_TCollection_ExtendedString_uint8_t",
        "TDataStd_DataMapOfStringReal": "DataMap_TCollection_ExtendedString_double",
        "TDataStd_DataMapOfStringString": "DataMap_TCollection_ExtendedString_TCollection_ExtendedString",
        "TDataStd_HLabelArray1": "HArray1_TDF_Label",
        "TDataStd_LabelArray1": "Array1_TDF_Label",
        "TDataStd_ListOfByte": "List_uint8_t",
        "TDataStd_ListOfExtendedString": "List_TCollection_ExtendedString",
    },
    "TDataXtd": {"TDataXtd_Array1OfTrsf": "Array1_gp_Trsf",},
    "TDocStd": {
        "TDocStd_SequenceOfApplicationDelta": "Sequence_TDocStd_ApplicationDelta",
        "TDocStd_SequenceOfDocument": "Sequence_TDocStd_Document",
    },
    "TFunction": {"TFunction_DoubleMapOfIntegerLabel": "DoubleMap_int_TDF_Label",},
    "TNaming": {
        "TNaming_ListOfNamedShape": "List_TNaming_NamedShape",
        "TNaming_MapOfNamedShape": "Map_TNaming_NamedShape",
    },
    "TObj": {
        "TObj_DataMapOfNameLabel": "DataMap_TCollection_HExtendedString_TDF_Label",
    },
    "TShort": {
        "TShort_Array1OfShortReal": "Array1_float",
        "TShort_HArray1OfShortReal": "HArray1_float",
    },
    "TopOpeBRep": {
        "TopOpeBRep_Array1OfLineInter": "Array1_TopOpeBRep_LineInter",
        "TopOpeBRep_HArray1OfLineInter": "HArray1_TopOpeBRep_LineInter",
        "TopOpeBRep_SequenceOfPoint2d": "Sequence_TopOpeBRep_Point2d",
    },
    "TopOpeBRepBuild": {
        "TopOpeBRepBuild_IndexedDataMapOfShapeVertexInfo": "IndexedDataMap_TopoDS_Shape_TopOpeBRepBuild_VertexInfo_TopTools_ShapeMapHasher",
        "TopOpeBRepBuild_ListOfLoop": "List_TopOpeBRepBuild_Loop",
        "TopOpeBRepBuild_ListOfPave": "List_TopOpeBRepBuild_Pave",
    },
    "TopOpeBRepDS": {
        "TopOpeBRepDS_DataMapOfShapeListOfShapeOn1State": "DataMap_TopoDS_Shape_TopOpeBRepDS_ListOfShapeOn1State_TopTools_ShapeMapHasher",
        "TopOpeBRepDS_DataMapOfShapeState": "DataMap_TopoDS_Shape_TopAbs_State_TopTools_ShapeMapHasher",
        "TopOpeBRepDS_IndexedDataMapOfShapeWithState": "IndexedDataMap_TopoDS_Shape_TopOpeBRepDS_ShapeWithState_TopTools_ShapeMapHasher",
        "TopOpeBRepDS_ListOfInterference": "List_TopOpeBRepDS_Interference",
        "TopOpeBRepDS_MapOfShapeData": "IndexedDataMap_TopoDS_Shape_TopOpeBRepDS_ShapeData_TopTools_ShapeMapHasher",
    },
    "TopOpeBRepTool": {
        "TopOpeBRepTool_IndexedDataMapOfShapeBox": "IndexedDataMap_TopoDS_Shape_Bnd_Box",
    },
    "TopTools": {
        "TopTools_Array1OfShape": "Array1_TopoDS_Shape",
        "TopTools_Array2OfShape": "Array2_TopoDS_Shape",
        "TopTools_DataMapOfIntegerListOfShape": "DataMap_int_List_TopoDS_Shape",
        "TopTools_DataMapOfIntegerShape": "DataMap_int_TopoDS_Shape",
        "TopTools_DataMapOfOrientedShapeInteger": "DataMap_TopoDS_Shape_int",
        "TopTools_DataMapOfShapeBox": "DataMap_TopoDS_Shape_Bnd_Box_TopTools_ShapeMapHasher",
        "TopTools_DataMapOfShapeInteger": "DataMap_TopoDS_Shape_int_TopTools_ShapeMapHasher",
        "TopTools_DataMapOfShapeListOfShape": "DataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_DataMapOfShapeReal": "DataMap_TopoDS_Shape_double_TopTools_ShapeMapHasher",
        "TopTools_DataMapOfShapeShape": "DataMap_TopoDS_Shape_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_HArray1OfShape": "HArray1_TopoDS_Shape",
        "TopTools_HArray2OfShape": "HArray2_TopoDS_Shape",
        "TopTools_HSequenceOfShape": "HSequence_TopoDS_Shape",
        "TopTools_IndexedDataMapOfShapeListOfShape": "IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_IndexedDataMapOfShapeReal": "IndexedDataMap_TopoDS_Shape_double_TopTools_ShapeMapHasher",
        "TopTools_IndexedDataMapOfShapeShape": "IndexedDataMap_TopoDS_Shape_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_IndexedMapOfOrientedShape": "IndexedMap_TopoDS_Shape",
        "TopTools_IndexedMapOfShape": "IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_ListOfListOfShape": "List_List_TopoDS_Shape",
        "TopTools_ListOfShape": "List_TopoDS_Shape",
        "TopTools_MapOfShape": "Map_TopoDS_Shape_TopTools_ShapeMapHasher",
        "TopTools_SequenceOfShape": "Sequence_TopoDS_Shape",
    },
    "Transfer": {
        "Transfer_HSequenceOfFinder": "HSequence_Transfer_Finder",
        "Transfer_SequenceOfFinder": "Sequence_Transfer_Finder",
    },
    "Units": {
        "Units_QtsSequence": "Sequence_Units_Quantity",
        "Units_QuantitiesSequence": "HSequence_Units_Quantity",
        "Units_TksSequence": "Sequence_Units_Token",
        "Units_TokensSequence": "HSequence_Units_Token",
        "Units_UnitsSequence": "HSequence_Units_Unit",
        "Units_UtsSequence": "Sequence_Units_Unit",
    },
    "V3d": {
        "V3d_ListOfLight": "List_Graphic3d_CLight",
        "V3d_ListOfView": "List_V3d_View",
    },
    "XCAFDimTolObjects": {
        "XCAFDimTolObjects_DatumModifiersSequence": "Sequence_XCAFDimTolObjects_DatumSingleModif",
        "XCAFDimTolObjects_DatumObjectSequence": "Sequence_XCAFDimTolObjects_DatumObject",
        "XCAFDimTolObjects_DimensionModifiersSequence": "Sequence_XCAFDimTolObjects_DimensionModif",
        "XCAFDimTolObjects_DimensionObjectSequence": "Sequence_XCAFDimTolObjects_DimensionObject",
        "XCAFDimTolObjects_GeomToleranceModifiersSequence": "Sequence_XCAFDimTolObjects_GeomToleranceModif",
        "XCAFDimTolObjects_GeomToleranceObjectSequence": "Sequence_XCAFDimTolObjects_GeomToleranceObject",
    },
    "XCAFDoc": {
        "XCAFDoc_DataMapOfShapeLabel": "DataMap_TopoDS_Shape_TDF_Label_TopTools_ShapeMapHasher",
    },
    "XCAFPrs": {
        "XCAFPrs_IndexedDataMapOfShapeStyle": "IndexedDataMap_TopoDS_Shape_XCAFPrs_Style_TopTools_ShapeMapHasher",
    },
    "gp": {"gp_Vec2f": "Vec2_float", "gp_Vec3f": "Vec3_float",},
}

# Static methods that OCCT 8 moved to another class (old owner, name) -> (module, new owner).
_MOVED_STATIC = {
    ("STEPCAFControl", "STEPCAFControl_GDTProperty", "IsDimensionalLocation_s"): (
        "XCAFDimTolObjects",
        "XCAFDimTolObjects_DimensionObject",
    ),
    ("STEPCAFControl", "STEPCAFControl_GDTProperty", "IsDimensionalSize_s"): (
        "XCAFDimTolObjects",
        "XCAFDimTolObjects_DimensionObject",
    ),
}


def enabled() -> bool:
    """True once :func:`enable` has run in this process."""

    return _enabled


def restored() -> Dict[str, str]:
    """The names :func:`enable` set, as ``{"Owner.name": kind}`` (empty before)."""

    return dict(_restored)


def calls() -> Dict[str, int]:
    """How many times each method enable() replaced (``Bnd_Box.Get`` ...) was called."""

    return dict(_calls)


def _count(name: str) -> None:
    _calls[name] = _calls.get(name, 0) + 1


def enable() -> Dict[str, str]:
    """Restore the OCP 7.x names on top of OCP 8 (see the module docstring).

    Safe to call any number of times from any thread; only the first call does
    work. Returns :func:`restored`.
    """

    global _enabled

    with _lock:
        if not _enabled:
            import OCP.OCP as ocp

            modules = _ocp_modules(ocp)
            done: Dict[str, str] = {}
            _restore_static_and_enums(modules, done)
            _restore_renamed(modules, done)
            _restore_moved(modules, done)
            _restore_bnd_get(modules, done)
            _restore_fclass2d(modules, done)
            _restored.update(done)
            _enabled = True

    return restored()


def _ocp_modules(ocp) -> Dict[str, object]:
    """Every OCP package module, by short name (``"TopoDS"``, ``"collections"`` ...)."""

    out = {}
    for name, value in vars(ocp).items():
        mod_name = getattr(value, "__name__", "")
        if type(value).__name__ == "module" and mod_name == "OCP.OCP." + name:
            out[name] = value
    return out


def _set(owner, name: str, value, key: str, kind: str, done: Dict[str, str]) -> None:
    """Set owner.name = value unless OCP already has that name."""

    if hasattr(owner, name):
        return
    setattr(owner, name, value)
    done[key] = kind


def _set_module(modules, mod_name: str, name: str, value, kind: str, done) -> None:
    """Set a module-level name on OCP.OCP.<mod> and, if it is already imported,
    on the OCP.<mod> package that re-exports it (a later import copies it)."""

    binary = modules[mod_name]
    package = sys.modules.get("OCP." + mod_name)
    owners = [binary] + (
        [package] if package is not None and package is not binary else []
    )
    if any(hasattr(owner, name) for owner in owners):
        return
    for owner in owners:
        setattr(owner, name, value)
    done[f"{mod_name}.{name}"] = kind


def _is_ocp_namespace(value) -> bool:
    return type(value).__name__ == "module" and getattr(
        value, "__name__", ""
    ).startswith("OCP.")


def _is_enum(value) -> bool:
    return isinstance(value, type) and isinstance(
        getattr(value, "__members__", None), dict
    )


def _restore_static_and_enums(modules, done) -> None:
    seen = set()
    for mod in modules.values():
        for owner_name, owner in list(vars(mod).items()):
            if id(owner) in seen:
                continue
            if _is_ocp_namespace(owner):
                # OCCT 8 namespaces (TopoDS::Face ...) are bound as submodules of
                # plain functions; OCP 7 had them as Face_s.
                seen.add(id(owner))
                for fname, func in list(vars(owner).items()):
                    if (
                        callable(func)
                        and not fname.startswith("_")
                        and not fname.endswith("_s")
                        and not isinstance(func, type)
                    ):
                        _set(
                            owner,
                            fname + "_s",
                            func,
                            f"{owner_name}.{fname}_s",
                            "static",
                            done,
                        )
            elif isinstance(owner, type) and not _is_enum(owner):
                seen.add(id(owner))
                for attr, raw in list(vars(owner).items()):
                    if attr.startswith("_"):
                        continue
                    if isinstance(raw, staticmethod) and not attr.endswith("_s"):
                        _set(
                            owner,
                            attr + "_s",
                            raw,
                            f"{owner.__name__}.{attr}_s",
                            "static",
                            done,
                        )
                    elif _is_enum(raw):
                        for member, value in raw.__members__.items():
                            _set(
                                owner,
                                member,
                                value,
                                f"{owner.__name__}.{member}",
                                "enum",
                                done,
                            )


def _restore_renamed(modules, done) -> None:
    collections = modules.get("collections")
    for mod_name, names in _RENAMED.items():
        mod = modules.get(mod_name)
        if mod is None:
            continue
        for old, new in names.items():
            if "." in new:
                target_mod, target_name = new.split(".", 1)
                target = getattr(modules.get(target_mod), target_name, None)
            else:
                target = getattr(collections, new, None)
            if target is not None:
                _set_module(modules, mod_name, old, target, "renamed", done)


def _restore_moved(modules, done) -> None:
    for (mod_name, owner_name, attr), (new_mod, new_owner) in _MOVED_STATIC.items():
        owner = getattr(modules.get(mod_name), owner_name, None)
        target = getattr(getattr(modules.get(new_mod), new_owner, None), attr, None)
        if owner is not None and target is not None:
            _set(
                owner, attr, staticmethod(target), f"{owner_name}.{attr}", "moved", done
            )


class _BoxLimits(tuple):
    """Bnd_Box.Get() result: unpacks as OCP 7's (xmin, ymin, zmin, xmax, ymax, zmax)
    and has OCCT 8's Bnd_Box::Limits fields."""

    __slots__ = ()

    @property
    def Xmin(self) -> float:
        return self[0]

    @property
    def Ymin(self) -> float:
        return self[1]

    @property
    def Zmin(self) -> float:
        return self[2]

    @property
    def Xmax(self) -> float:
        return self[3]

    @property
    def Ymax(self) -> float:
        return self[4]

    @property
    def Zmax(self) -> float:
        return self[5]


class _Box2dLimits(tuple):
    """Bnd_Box2d.Get() result: unpacks as OCP 7's (xmin, ymin, xmax, ymax) and has
    OCCT 8's Bnd_Box2d::Limits fields."""

    __slots__ = ()

    @property
    def Xmin(self) -> float:
        return self[0]

    @property
    def Ymin(self) -> float:
        return self[1]

    @property
    def Xmax(self) -> float:
        return self[2]

    @property
    def Ymax(self) -> float:
        return self[3]


def _bnd_box_get(self) -> Tuple[float, ...]:
    # CornerMin/CornerMax are OCCT's old Get(): the gap is included, open sides
    # give -/+1e100, and a void box raises Standard_ConstructionError.
    _count("Bnd_Box.Get")
    lo = self.CornerMin()
    hi = self.CornerMax()
    return _BoxLimits((lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()))


def _bnd_box2d_get(self) -> Tuple[float, ...]:
    _count("Bnd_Box2d.Get")
    if self.IsVoid():
        from OCP.Standard import Standard_ConstructionError

        raise Standard_ConstructionError("Bnd_Box is void")
    return _Box2dLimits(
        (self.GetXMin(), self.GetYMin(), self.GetXMax(), self.GetYMax())
    )


def _restore_bnd_get(modules, done) -> None:
    """OCP 8.0.1 binds Get() -> Bnd_Box::Limits without binding Limits, so every
    call raises TypeError. Only then is Get replaced; a working binding is kept."""

    bnd = modules.get("Bnd")
    probes = (
        ("Bnd_Box", _bnd_box_get, (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)),
        ("Bnd_Box2d", _bnd_box2d_get, (0.0, 0.0, 1.0, 1.0)),
    )
    for name, getter, corners in probes:
        cls = getattr(bnd, name, None)
        if cls is None:
            continue
        box = cls()
        box.Update(*corners)
        try:
            box.Get()
            continue  # the binding works: leave it alone
        except TypeError:
            pass
        setattr(cls, "Get", getter)
        done[f"{name}.Get"] = "patched"


def _restore_fclass2d(modules, done) -> None:
    if "BRepTopAdaptor" in modules:
        _set_module(
            modules,
            "BRepTopAdaptor",
            "BRepTopAdaptor_FClass2d",
            BRepTopAdaptor_FClass2d,
            "class",
            done,
        )


def _is_degenerated(curve, first: float, last: float) -> bool:
    from OCP.Precision import Precision

    step = (last - first) * 0.1
    start = curve.Value(first)
    current = first
    while current < last:
        if start.SquareDistance(curve.Value(current)) > Precision.Confusion_s():
            return False
        nxt = current + step
        current = nxt if nxt != current else math.nextafter(current, last)
    return True


class BRepTopAdaptor_FClass2d:
    """Classifies 2D (u, v) points against a face's boundaries.

    A stand-in for OCCT's BRepTopAdaptor_FClass2d, which OCP 8 no longer binds:
    the same constructor and methods, implemented with OCCT's algorithm
    (BRepTopAdaptor_FClass2d.cxx, unchanged from OCCT 7.9 to 8.0) on the
    classes OCP 8 does bind, so it gives the same answers.
    """

    def __init__(self, F, Tol: float):
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import (
            BRepAdaptor_Curve,
            BRepAdaptor_Curve2d,
            BRepAdaptor_Surface,
        )
        from OCP.BRepTools import BRepTools_WireExplorer
        from OCP.CSLib import CSLib_Class2d
        from OCP.ElCLib import ElCLib
        from OCP.GCPnts import GCPnts_QuasiUniformDeflection
        from OCP.Geom2dInt import Geom2dInt_Geom2dCurveTool
        from OCP.Precision import Precision
        from OCP.TopAbs import (
            TopAbs_EDGE,
            TopAbs_FORWARD,
            TopAbs_REVERSED,
            TopAbs_WIRE,
        )
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopoDS import TopoDS, TopoDS_Vertex
        from OCP.gp import gp_Dir2d, gp_Lin2d, gp_Pnt, gp_Pnt2d, gp_Vec2d
        from OCP.collections import Array1_gp_Pnt2d

        self._toluv = Tol
        face = TopoDS.Face(F.Oriented(TopAbs_FORWARD))
        self._face = face
        surf = BRepAdaptor_Surface()
        surf.Initialize(F, False)
        self._uper = surf.IsUPeriodic()
        self._vper = surf.IsVPeriodic()
        self._uperiod = surf.UPeriod() if self._uper else 0.0
        self._vperiod = surf.VPeriod() if self._vper else 0.0
        self._tabclass = []
        self._taborien = []
        self.Umin = self.Vmin = 0.0
        self.Umax = self.Vmax = -self.Umin

        confusion = Precision.Confusion_s()
        eps = 1.0e-10

        def array(points):
            arr = Array1_gp_Pnt2d(1, len(points))
            for i, p in enumerate(points, 1):
                arr.SetValue(i, p)
            return arr

        def fleche(seq, fu, fv):
            # deflection of the middle of the last three points from their chord
            lin = gp_Lin2d(seq[-3], gp_Dir2d(gp_Vec2d(seq[-3], seq[-1])))
            pp = ElCLib.Value_s(ElCLib.Parameter_s(lin, seq[-2]), lin)
            du = abs(pp.X() - seq[-2].X())
            dv = abs(pp.Y() - seq[-2].Y())
            return max(fu, du), max(fv, dv)

        def square_and_perimeter(seq):
            # OCCT's loop: im1 trails im0 by one, wrapping once to the start
            n = len(seq)
            pts = [None] * (n + 1)
            pts[n - 1] = seq[n - 2]
            pts[n] = seq[n - 1]
            square = per = 0.0
            im1 = n - 1
            im0 = 1
            for ii in range(1, n):
                if im1 >= n:
                    im1 = 1
                pts[ii] = seq[ii - 1]
                a = pts[im0]
                b = pts[im1]
                square += (a.X() - b.X()) * (a.Y() + b.Y()) * 0.5
                dx = a.X() - b.X()
                dy = a.Y() - b.Y()
                per += math.sqrt(dx * dx + dy * dy)
                im0 += 1
                im1 += 1
            return pts[1:], square, per

        n_edges_in_wire = 0
        bad_wire = False
        wires = TopExp_Explorer(face, TopAbs_WIRE)
        while wires.More() and not bad_wire:
            wire = TopoDS.Wire(wires.Current())
            nbpnts = 0
            seq = []
            firstpoint = 1
            fu = fv = 0.0
            wire_not_empty = False
            nb_edges = 0
            counter = TopExp_Explorer(wire, TopAbs_EDGE)
            while counter.More():
                nb_edges += 1
                counter.Next()
            n_edges_in_wire = nb_edges
            prev3d = gp_Pnt(0, 0, 0)
            prev3d_set = False

            explorer = BRepTools_WireExplorer()
            explorer.Init(wire, face)
            while explorer.More():
                nb_edges -= 1
                edge = explorer.Current()
                orient = edge.Orientation()
                if orient == TopAbs_FORWARD or orient == TopAbs_REVERSED:
                    if BRep_Tool.CurveOnSurface_s(edge, face, 0.0, 0.0) is None:
                        return
                    first, last = BRep_Tool.Range_s(edge, face)
                    if abs(last - first) < 1.0e-9:
                        explorer.Next()
                        continue
                    degenerated = BRep_Tool.Degenerated_s(edge) or BRep_Tool.IsClosed_s(
                        edge, face
                    )
                    va, vb = TopoDS_Vertex(), TopoDS_Vertex()
                    TopExp.Vertices_s(edge, va, vb)
                    if va.IsNull() or vb.IsNull():
                        degenerated = True
                    c2d = BRepAdaptor_Curve2d(edge, face)
                    c3d = BRepAdaptor_Curve(edge, face)
                    if not degenerated:
                        degenerated = _is_degenerated(c3d, first, last)

                    nbs = Geom2dInt_Geom2dCurveTool.NbSamples_s(c2d)
                    if nbs > 2:
                        nbs *= 4
                    du = (last - first) / float(nbs - 1)
                    if orient == TopAbs_FORWARD:
                        u = first
                    else:
                        u = last
                        du = -du
                    if firstpoint == 2:
                        u += du
                    before = nbpnts
                    for _ in range(firstpoint, nbs + 1):
                        p2d = c2d.Value(u)
                        x, y = p2d.X(), p2d.Y()
                        if x < self.Umin:
                            self.Umin = x
                        if x > self.Umax:
                            self.Umax = x
                        if y < self.Vmin:
                            self.Vmin = y
                        if y > self.Vmax:
                            self.Vmax = y
                        dist = 1.0e20
                        p3d = gp_Pnt()
                        if not degenerated:
                            p3d = c3d.Value(u)
                            if nbpnts > 1 and prev3d_set:
                                dist = p3d.Distance(prev3d)
                        real = True
                        if dist < confusion:
                            if p3d.Distance(c3d.Value(u - du / 2.0)) < confusion:
                                real = False
                        if real:
                            if not degenerated:
                                prev3d = p3d
                                prev3d_set = True
                            nbpnts += 1
                            seq.append(p2d)
                        u += du
                        if nbpnts > before + 4 and seq[-3].SquareDistance(seq[-1]):
                            fu, fv = fleche(seq, fu, fv)
                    if firstpoint == 1:
                        firstpoint = 2
                    wire_not_empty = True
                explorer.Next()

            if nb_edges:
                # the wire explorer missed edges: classify with the face classifier
                self._tabclass.append(
                    CSLib_Class2d(
                        array([gp_Pnt2d(0.0, 0.0), gp_Pnt2d(0.0, 0.0)]),
                        fu,
                        fv,
                        self.Umin,
                        self.Vmin,
                        self.Umax,
                        self.Vmax,
                    )
                )
                bad_wire = True
                self._taborien.append(-1)
            elif wire_not_empty:
                if nbpnts > 3:
                    pclass, square, per = square_and_perimeter(seq)
                    exp_thick = max(2.0 * abs(square) / per, 1e-7)
                    defl = max(fu, fv)
                    discr_defl = min(defl * 0.1, exp_thick * 10.0)
                    while defl > exp_thick and discr_defl > 1e-7:
                        # too coarse for this area/perimeter ratio: discretize again
                        firstpoint = 1
                        seq = []
                        fu = fv = 0.0
                        explorer.Init(wire, face)
                        while explorer.More():
                            edge = explorer.Current()
                            orient = edge.Orientation()
                            if orient == TopAbs_FORWARD or orient == TopAbs_REVERSED:
                                first, last = BRep_Tool.Range_s(edge, face)
                                if abs(last - first) < 1.0e-9:
                                    explorer.Next()
                                    continue
                                c2d = BRepAdaptor_Curve2d(edge, face)
                                discr = GCPnts_QuasiUniformDeflection(c2d, discr_defl)
                                if not discr.IsDone():
                                    break
                                nbp = discr.NbPoints()
                                step, i, end = 1, 1, nbp + 1
                                if orient == TopAbs_REVERSED:
                                    step, i, end = -1, nbp, 0
                                if firstpoint == 2:
                                    i += step
                                while i != end:
                                    seq.append(c2d.Value(discr.Parameter(i)))
                                    i += step
                                if nbp > 2:
                                    fu, fv = fleche(seq, fu, fv)
                                firstpoint = 2
                            explorer.Next()
                        nbpnts = len(seq)
                        pclass, square, per = square_and_perimeter(seq)
                        exp_thick = max(2.0 * abs(square) / per, 1e-7)
                        defl = max(fu, fv)
                        discr_defl = min(discr_defl * 0.1, exp_thick * 10.0)

                    if (
                        n_edges_in_wire == 1
                        and fu < eps
                        and fv < eps
                        and abs(square) < eps
                    ):
                        self._taborien.append(1)
                    else:
                        self._taborien.append(1 if square < 0.0 else 0)
                    if fu < Tol:
                        fu = Tol
                    if fv < Tol:
                        fv = Tol
                    self._tabclass.append(
                        CSLib_Class2d(
                            array(pclass),
                            fu,
                            fv,
                            self.Umin,
                            self.Vmin,
                            self.Umax,
                            self.Vmax,
                        )
                    )
                else:
                    bad_wire = True
                    self._taborien.append(-1)
                    self._tabclass.append(
                        CSLib_Class2d(
                            array(seq[:2]),
                            fu,
                            fv,
                            self.Umin,
                            self.Vmin,
                            self.Umax,
                            self.Vmax,
                        )
                    )
            wires.Next()

        if self._tabclass and bad_wire:
            self._taborien[0] = -1

    def PerformInfinitePoint(self):
        from OCP.TopAbs import TopAbs_IN
        from OCP.gp import gp_Pnt2d

        big = 1.7976931348623157e308  # RealLast()
        if (
            self.Umax == -big
            or self.Vmax == -big
            or self.Umin == big
            or self.Vmin == big
        ):
            return TopAbs_IN
        p = gp_Pnt2d(
            self.Umin - (self.Umax - self.Umin), self.Vmin - (self.Vmax - self.Vmin)
        )
        return self.Perform(p, False)

    def Perform(self, Puv, RecadreOnPeriodic: bool = True):
        return self._classify(Puv, None, RecadreOnPeriodic)

    def TestOnRestriction(self, Puv, Tol: float, RecadreOnPeriodic: bool = True):
        return self._classify(Puv, Tol, RecadreOnPeriodic)

    def Destroy(self) -> None:
        pass

    def _classify(self, puv, on_tol, recadre):
        from OCP.BRepClass import BRepClass_FaceClassifier
        from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT, TopAbs_UNKNOWN
        from OCP.gp import gp_Pnt2d

        if not self._tabclass:
            return TopAbs_IN
        u = uu = puv.X()
        v = vv = puv.Y()
        uper, vper = self._uper, self._vper
        uperiod, vperiod = self._uperiod, self._vperiod
        status = TopAbs_UNKNOWN
        urecadre = vrecadre = False

        if recadre:
            if uper:
                if uu < self.Umin:
                    while uu < self.Umin:
                        uu += uperiod
                else:
                    while uu >= self.Umin:
                        uu -= uperiod
                    uu += uperiod
            if vper:
                if vv < self.Vmin:
                    while vv < self.Vmin:
                        vv += vperiod
                else:
                    while vv >= self.Vmin:
                        vv -= vperiod
                    vv += vperiod

        while True:
            inside = 1
            p = gp_Pnt2d(u, v)
            if self._taborien[0] != -1:
                for klass, orien in zip(self._tabclass, self._taborien):
                    cur = int(
                        klass.SiDans(p)
                        if on_tol is None
                        else klass.SiDans_OnMode(p, on_tol)
                    )
                    if cur == 1:
                        if orien == 0:
                            inside = -1
                            break
                    elif cur == -1:
                        if orien == 1:
                            inside = -1
                            break
                    else:
                        inside = 0
                        break
                if inside == 0:
                    if on_tol is None:
                        classifier = BRepClass_FaceClassifier()
                        classifier.Perform(self._face, p, min(self._toluv, 4.0))
                        status = classifier.State()
                    else:
                        status = TopAbs_ON
                elif inside == 1:
                    status = TopAbs_IN
                else:
                    status = TopAbs_OUT
            else:
                # a wire could not be sampled: use the face classifier
                classifier = BRepClass_FaceClassifier()
                classifier.Perform(
                    self._face, p, self._toluv if on_tol is None else on_tol
                )
                status = classifier.State()

            if not recadre or (not uper and not vper):
                return status
            if status == TopAbs_IN or status == TopAbs_ON:
                return status

            if not urecadre:
                u = uu
                urecadre = True
            elif uper:
                u += uperiod
            if u > self.Umax or not uper:
                if not vrecadre:
                    v = vv
                    vrecadre = True
                elif vper:
                    v += vperiod
                u = uu
                if v > self.Vmax or not vper:
                    return status
