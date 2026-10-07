import io
import zipfile
from pathlib import Path
import numpy as np
import bpy

from .utils import parse_marvelous_designer_map, get_transform_from_matrix2d
from .. import IOFormatBase
from ....model.qianyi_project import QianyiProject
from ....model.pattern import Pattern
from ....declarations import Panels
from ....utilities.node_tree import set_active_node_tree


class HalfSewing:
    def __init__(self, pattern, start_edge, end_edge, start_pos, end_pos, reverse):
        self.pattern = pattern
        self.start_edge = start_edge
        self.end_edge = end_edge
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.reverse = reverse

    def reverse_by_pattern(self, pattern):
        edges_size_ = len(pattern.edges) - 1
        self.start_edge = edges_size_ - self.start_edge
        self.end_edge = edges_size_ - self.end_edge
        self.start_pos = 1. - self.start_pos
        self.end_pos = 1. - self.end_pos
        self.reverse = not self.reverse


class MarvelousIO(IOFormatBase):
    ext = ".zpac"

    def import_file(self, context, filepath, temp_dir):
        with open(filepath, 'rb') as f:
            compressed_data = f.read()
        with zipfile.ZipFile(io.BytesIO(compressed_data), 'r') as zip_file:
            pac_name = next((f for f in zip_file.namelist() if f.endswith('.pac')), None)
            if not pac_name: return False
            project_name = Path(pac_name).stem
            pac_dir = Path(temp_dir, project_name)
            pac_dir.mkdir(exist_ok=True)
            zip_file.extractall(pac_dir)
            with open(pac_dir / pac_name, 'rb') as f:
                data = f.read()
            objs = parse_marvelous_designer_map(data)
            address = objs['uiVersion']
            version = np.frombuffer(data[address[1]:address[1] + address[2]], dtype=np.int32)[0]
            if not version >= 1001:
                raise Exception(f"Marvelous designer version {version} not supported!")

            def parse_float32(meta):
                res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.float32)
                return res[0]

            def parse_uint32(meta):
                res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.uint32)
                return res[0] if res.shape[0] == 1 else res

            def parse_xy(meta):
                res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.float32)
                return res.reshape(-1, 2) if res.shape[0] > 2 else res

            def parse_bool(meta):
                res = np.frombuffer(data[meta[1]:meta[1] + meta[2]], dtype=np.bool)
                return bool(res[0])

            project: QianyiProject = bpy.data.node_groups.new(project_name, Panels.QianyiNodeTree)
            project.name = project_name
            set_active_node_tree(context, project)
            md_patterns = objs["mapPatternEditor"]["mapPatternList"]["listPattern"]
            pattern_reversed = []
            for md_pattern in md_patterns:
                # name
                name_meta = md_pattern["mapElement"]["qsNameUTF8"]
                pattern_name = data[name_meta[1]:name_meta[1] + name_meta[2]].decode('utf-8')
                pattern: Pattern = project.add_pattern()
                pattern.name = pattern_name
                # granularity
                granularity = parse_float32(md_pattern['fEdgeLength'])
                pattern.granularity = granularity
                # matrix and points
                matrix_meta = md_pattern["mapShape2D"]["mapTransformer2D"]["m3Matrix"]
                M = np.frombuffer(data[matrix_meta[1]:matrix_meta[1] + matrix_meta[2]], dtype=np.float32).reshape(-1, 3)
                translate, scale, rotation = get_transform_from_matrix2d(M)
                pattern.anchor = translate
                for point in md_pattern["mapShape2D"]["listPoint"]:
                    pos = M[:2, :2].T @ parse_xy(point["v2Position"])
                    pattern.add_vertex(pos)
                for line in md_pattern["mapShape2D"]["listLine"]:
                    iLineType = np.frombuffer(data[line["iLineType"][1]:line["iLineType"][1] + 4], dtype=np.uint32)[0]
                    index1, index2 = parse_uint32(line["uiStartPointIndex"]), parse_uint32(line["uiEndPointIndex"])
                    if "listPoint" in line:
                        lineListPoint = line["listPoint"]
                        if iLineType == 3:
                            c1 = M[:2, :2].T @ parse_xy(lineListPoint[0]["v2Position"])
                            c2 = M[:2, :2].T @ parse_xy(lineListPoint[1]["v2Position"])
                            pattern.add_edge(index1, index2, c1, c2, "FREE", "FREE", update=False)
                        elif iLineType == 2:
                            edge = pattern.add_edge(index1, index2, update=False)
                            for p in lineListPoint:
                                edge.add_edge_point(M[:2, :2].T @ parse_xy(p["v2Position"]))
                            edge.update()
                    elif iLineType == 0:
                        pattern.add_edge(index1, index2, update=False)
                ccw_before = pattern.ensure_edge_ccw()
                pattern_reversed.append(not ccw_before)

            # sewing
            def parse_half_sewing(hs):
                half_sewing = HalfSewing(pattern=parse_uint32(hs['uiSelfIndex']),
                                         start_edge=parse_uint32(hs['uiStartIndex']),
                                         end_edge=parse_uint32(hs['uiEndIndex']),
                                         start_pos=parse_float32(hs['fRatioStart']),
                                         end_pos=parse_float32(hs['fRatioEnd']),
                                         reverse=not parse_bool(hs['bDirection']))
                return half_sewing

            # sewings = []
            for slpg in objs["mapPatternEditor"]['mapSeamLinePairGroup']['listSeamLinePairGroup']:
                # sewing = {}
                # sewings.append(sewing)
                name_meta = slpg["mapElement"]["qsNameUTF8"]
                name = data[name_meta[1]:name_meta[1] + name_meta[2]].decode('utf-8')
                # sewing['name'] = name
                # TODO MtoN
                seam_line_pair = slpg['mapSeamLinePairList']['listSeamLinePair'][0]
                seams: list[HalfSewing] = []
                seams.append(parse_half_sewing(seam_line_pair['mapSeamLine0']["mapParamLine"]))
                seams.append(parse_half_sewing(seam_line_pair['mapSeamLine1']["mapParamLine"]))
                for seam in seams:
                    seam_pattern = seam.pattern
                    if pattern_reversed[seam_pattern]:
                        seam.reverse_by_pattern(project.patterns[seam_pattern])

                # def add_sewing(self, side1_line1, side1_pos1, side1_line2, side1_pos2,side2_line1, side2_pos1, side2_line2, side2_pos2):
                p1 = project.patterns[seams[0].pattern]
                p2 = project.patterns[seams[1].pattern]

                sw = project.add_sewing(p1.edges[seams[0].start_edge], seams[0].start_pos,
                                        p1.edges[seams[0].end_edge], seams[0].end_pos,
                                        seams[0].reverse,
                                        p2.edges[seams[1].start_edge], seams[1].start_pos,
                                        p2.edges[seams[1].end_edge], seams[1].end_pos,
                                        seams[1].reverse, update=False)
                sw.name = name
            project.calc_all_sewings_sections()
        return True
