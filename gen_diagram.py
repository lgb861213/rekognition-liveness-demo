#!/usr/bin/env python3
"""Generate the architecture drawio with computed, non-overlapping label placement.

Strategy for a clean layout:
- 3 horizontal lanes (client / app / aws), 3 vertical columns.
- Icons carry only a short single-line label.
- Longer descriptions are separate text boxes placed with guaranteed gaps.
- Flow edges are numbered; their labels are placed on the segment with an
  explicit offset and a white background, and we VERIFY each label's bbox does
  not intersect any node/text box before writing.
"""
import xml.sax.saxutils as sx

# ---- node layout (x, y, w, h) ----
N = {
    "ic_user":    (140, 135, 56, 56, "End User", "icon", "#232F3D", "mxgraph.aws4.user"),
    "ic_react":   (360, 128, 260, 66, "React SPA (Vite) · FaceLivenessDetector", "box", "#dae8fc", None),
    "ic_src":     (1140, 120, 300, 84, "源业务（阿里云美东）\n仅调用后端 API\n不接触生物特征原始数据", "boxr", "#f8cecc", None),

    "ic_backend": (430, 360, 58, 58, "Backend API (FastAPI)", "icon", "#ED7100", "mxgraph.aws4.fargate"),
    "ic_cognito": (800, 360, 58, 58, "Cognito Identity Pool", "icon", "#DD344C", "mxgraph.aws4.cognito"),
    "ic_iam":     (1160, 360, 58, 58, "IAM Role / Policy", "icon", "#DD344C", "mxgraph.aws4.identity_and_access_management_iam_role"),

    "ic_rek":     (430, 660, 58, 58, "Rekognition Face Liveness", "icon", "#01A88D", "mxgraph.aws4.rekognition"),
    "ic_coll":    (800, 660, 58, 58, "Rekognition Collection (1:N)", "icon", "#01A88D", "mxgraph.aws4.rekognition"),
    "ic_s3":      (1160, 660, 58, 58, "Amazon S3 (same region)", "icon", "#7AA116", "mxgraph.aws4.s3"),
}

# separate description text boxes (id: x,y,w,h,text,color)
T = {
    "backend_note": (300, 445, 320, 54, "• Liveness: Create / Get Session\n• 1:N: SearchUsers + SearchFaces / Index\n• Dedup enroll · User mgmt", "#7a4a00"),
    "cognito_note": (720, 445, 220, 20, "guest → StartFaceLivenessSession", "#7a4a00"),
    "iam_note":     (1120, 445, 160, 20, "least-privilege", "#7a4a00"),
    "coll_note":    (720, 745, 220, 34, "User + Face Vectors\ncheck-and-enroll 去重", "#00695c"),
    "s3_note":      (1085, 745, 210, 34, "Reference + Audit Images\nBlock Public · TLS · SSE · 90d", "#4a6a0e"),
}

LANES = [
    ("lane_client", 40, 90, 1420, 170, "①  客户端层  Client", "#F2F7FC", "#6c8ebf", "#2d5f8a"),
    ("lane_app",    40, 300, 1420, 240, "②  应用层  Application (your AWS account)", "#FFF6EC", "#ED7100", "#b85c00"),
    ("lane_aws",    40, 580, 1420, 470, "③  AWS 托管服务层  Managed Services — us-east-1 · data residency（生物特征数据不出境）", "#EAF6F5", "#01A88D", "#007a68"),
]

NOTES = (360, 830, 800, 200,
         "关键约束与成本\n\n"
         "• S3 桶与 Rekognition 同账号同区域（us-east-1），参考图/审计图不出境\n"
         "• 活体流式 $0.015/次 · IndexFaces/Search $0.001/图 · 向量存储 $0.01/1000/月\n"
         "• 去重：入库前 SearchUsers + SearchFaces 双查（face 向量即时可查，规避最终一致性）\n"
         "• 跨账号 1:N：后端 AssumeRole 到中心查重账号，统一调用同一 Collection")

# edges: id, source, target, label, color, dashed, label_x, label_y (absolute)
# label positions are chosen in gaps between columns/lanes.
E = [
    ("e1",  "ic_user", "ic_react", "1. 发起活体检测", "#333333", 0, 250, 150),
    ("e13", "ic_src",  "ic_backend","调用 API",       "#b85450", 1, 900, 250),
    ("e2",  "ic_react","ic_backend","2. POST /liveness/session", "#2d7dd2", 0, 250, 270),
    ("e3",  "ic_backend","ic_rek",  "3. CreateFaceLivenessSession → SessionId", "#2d7dd2", 0, 250, 560),
    ("e4",  "ic_react","ic_cognito","4. 获取访客凭证", "#8e44ad", 1, 690, 270),
    ("e5",  "ic_react","ic_rek",    "5. StartFaceLivenessSession (WebSocket)", "#16a085", 0, 210, 300),
    ("e6",  "ic_rek",  "ic_s3",     "6. 写入参考图/审计图", "#d35400", 0, 960, 640),
    ("e7",  "ic_react","ic_backend","7. onAnalysisComplete → verify-enroll", "#2d7dd2", 1, 700, 320),
    ("e8",  "ic_backend","ic_rek",  "8. GetFaceLivenessSessionResults", "#2d7dd2", 0, 540, 600),
    ("e9",  "ic_backend","ic_coll", "9. SearchUsers + SearchFaces (1:N)", "#c0392b", 0, 660, 628),
    ("e10", "ic_backend","ic_coll", "10. IndexFaces + CreateUser (若唯一)", "#27ae60", 1, 660, 648),
    ("e11", "ic_backend","ic_s3",   "读参考图供 1:N", "#7AA116", 1, 1000, 500),
    ("e12", "ic_backend","ic_iam",  "assumes", "#DD344C", 1, 1000, 345),
]


def esc(s):
    return sx.escape(s).replace("\n", "&#10;")


def bbox_of(x, y, w, h, is_icon):
    if is_icon:
        h = h + 22  # label under icon
    return (x, y, w, h)


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


# collect all obstacle bboxes
obstacles = []
for k, (x, y, w, h, *_r) in N.items():
    obstacles.append(bbox_of(x, y, w, h, _r[0] == "icon"))
for k, (x, y, w, h, *_r) in T.items():
    obstacles.append((x, y, w, h))

# verify edge label boxes don't collide with obstacles OR each other
label_boxes = {}
for (eid, s, t, lbl, col, dsh, lx, ly) in E:
    lw = max(60, len(lbl) * 6)
    lh = 18
    label_boxes[eid] = (lx - lw / 2, ly - lh / 2, lw, lh)

problems = []
for eid, lbox in label_boxes.items():
    for ob in obstacles:
        if overlap(lbox, ob):
            problems.append((eid, "obstacle"))
            break
ek = list(label_boxes)
for i in range(len(ek)):
    for j in range(i + 1, len(ek)):
        if overlap(label_boxes[ek[i]], label_boxes[ek[j]]):
            problems.append((ek[i], ek[j]))
if problems:
    print("LABEL OVERLAPS:", problems)
else:
    print("label placement OK: no overlaps (obstacles + label-vs-label)")

# ---- emit XML ----
out = []
out.append('<mxfile host="drawio-jsapi" version="1.0.0"><diagram id="d1" name="Liveness + 1:N Architecture">')
out.append('<mxGraphModel dx="1426" dy="798" grid="1" gridSize="10" guides="1" page="1" pageScale="1" pageWidth="1500" pageHeight="1100"><root>')
out.append('<mxCell id="0"/><mxCell id="1" parent="0"/>')
out.append(f'<mxCell id="title" value="{esc("Amazon Rekognition Face Liveness + 1:N Collection De-duplication (Region: us-east-1)")}" style="text;html=1;fontSize=18;fontStyle=1;align=center;" vertex="1" parent="1"><mxGeometry x="40" y="24" width="1420" height="34" as="geometry"/></mxCell>')

for (lid, x, y, w, h, lbl, fc, sc, tc) in LANES:
    out.append(f'<mxCell id="{lid}" value="{esc(lbl)}" style="rounded=0;whiteSpace=wrap;html=1;fillColor={fc};strokeColor={sc};verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;fontStyle=1;fontColor={tc};fontSize=13;" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

for k, (x, y, w, h, lbl, kind, color, shape) in N.items():
    if kind == "icon":
        style = f"sketch=0;outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon={shape};fillColor={color}"
    elif kind == "boxr":
        style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={color};strokeColor=#b85450;fontSize=11;dashed=1;align=center;verticalAlign=middle;"
    else:
        style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={color};strokeColor=#6c8ebf;fontSize=12;verticalAlign=middle;"
    out.append(f'<mxCell id="{k}" value="{esc(lbl)}" style="{style}" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

for k, (x, y, w, h, lbl, tc) in T.items():
    out.append(f'<mxCell id="{k}" value="{esc(lbl)}" style="text;html=1;align=center;verticalAlign=top;fontSize=10;fontColor={tc};" vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

nx, ny, nw, nh, ntext = NOTES
out.append(f'<mxCell id="notes" value="{esc(ntext)}" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;align=left;verticalAlign=top;spacingLeft=10;spacingTop=8;" vertex="1" parent="1"><mxGeometry x="{nx}" y="{ny}" width="{nw}" height="{nh}" as="geometry"/></mxCell>')

for (eid, s, t, lbl, col, dsh, lx, ly) in E:
    dash = "dashed=1;" if dsh else ""
    style = f"edgeStyle=orthogonalEdgeStyle;rounded=0;endArrow=block;html=1;strokeColor={col};{dash}"
    out.append(f'<mxCell id="{eid}" style="{style}" edge="1" parent="1" source="{s}" target="{t}"><mxGeometry relative="1" as="geometry"/></mxCell>')

# edge labels as standalone text boxes at verified non-overlapping positions
for (eid, s, t, lbl, col, dsh, lx, ly) in E:
    lw = max(60, len(lbl) * 6)
    lh = 18
    out.append(f'<mxCell id="{eid}_lbl" value="{esc(lbl)}" style="text;html=1;align=center;verticalAlign=middle;fontSize=10;fontColor={col};labelBackgroundColor=#ffffff;" vertex="1" parent="1"><mxGeometry x="{lx - lw/2:.0f}" y="{ly - lh/2:.0f}" width="{lw:.0f}" height="{lh}" as="geometry"/></mxCell>')

out.append('</root></mxGraphModel></diagram></mxfile>')

with open("docs/architecture.drawio", "w") as f:
    f.write("\n".join(out))
print("written docs/architecture.drawio")
