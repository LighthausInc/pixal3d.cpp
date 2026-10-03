"""Headless deterministic cleanup, GLB metrics and eight matched-camera renders."""
import bpy, bmesh, argparse, json, math, pathlib, sys
from mathutils import Vector

def args():
    p=argparse.ArgumentParser(); p.add_argument('--input',required=True); p.add_argument('--output',required=True); p.add_argument('--budget',type=int,required=True); p.add_argument('--height',type=float,required=True); p.add_argument('--resolution',type=int,default=512); return p.parse_args(sys.argv[sys.argv.index('--')+1:])

def meshes(): return [o for o in bpy.context.scene.objects if o.type=='MESH']
def metrics(height):
    tris=components=boundary_edges=boundary_loops=nonmanifold=loose_vertices=wire_edges=0; density_num=density_den=0.; textures={}
    for im in bpy.data.images:
        if im.source!='VIEWER' and im.size[0]>0: textures[im.name]={'width':im.size[0],'height':im.size[1],'channels':im.channels}
    pts=[o.matrix_world@Vector(c) for o in meshes() for c in o.bound_box]
    zspan=max(p.z for p in pts)-min(p.z for p in pts) if pts else 0
    scale=height/zspan if zspan else 1
    for o in meshes():
        me=o.data; me.calc_loop_triangles(); tris+=len(me.loop_triangles)
        # Weld only a temporary metric copy: GLB UV seams duplicate vertices.
        bm=bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6)
        loose_vertices+=sum(not v.link_faces for v in bm.verts); wire_edges+=sum(not e.link_faces for e in bm.edges)
        remaining={v for v in bm.verts if v.link_faces}
        while remaining:
            components+=1; todo=[remaining.pop()]
            while todo:
                for e in todo.pop().link_edges:
                    for v in e.verts:
                        if v in remaining: remaining.remove(v); todo.append(v)
        be={e for e in bm.edges if e.is_boundary}; boundary_edges+=len(be); nonmanifold+=sum(not e.is_manifold and not e.is_boundary and bool(e.link_faces) for e in bm.edges)
        while be:
            group={be.pop()}; todo=list(group)
            while todo:
                for v in todo.pop().verts:
                    for e in v.link_edges:
                        if e in be: be.remove(e); group.add(e); todo.append(e)
            degree={v:sum(e in group for e in v.link_edges) for e in group for v in e.verts}
            if all(n==2 for n in degree.values()): boundary_loops+=1
        bm.free()
        uv=me.uv_layers.active
        if uv:
            for t in me.loop_triangles:
                xyz=[o.matrix_world@me.vertices[i].co for i in t.vertices]; area=(xyz[1]-xyz[0]).cross(xyz[2]-xyz[0]).length*.5*scale**2
                u=[uv.data[i].uv for i in t.loops]; ua=abs((u[1].x-u[0].x)*(u[2].y-u[0].y)-(u[2].x-u[0].x)*(u[1].y-u[0].y))*.5
                px=0
                if t.material_index<len(o.material_slots):
                    m=o.material_slots[t.material_index].material
                    if m and m.use_nodes:
                        imgs=[n.image for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]
                        if imgs: px=imgs[0].size[0]*imgs[0].size[1]
                if px and area: density_num+=ua*px; density_den+=area
    return {'triangles':tris,'connected_components':components,'loose_vertices':loose_vertices,'wire_edges':wire_edges,'boundary_edges':boundary_edges,'holes_boundary_loops':boundary_loops,'nonmanifold_edges':nonmanifold,'uv_texel_density_px_per_m':math.sqrt(density_num/density_den) if density_den else None,'density_note':'Area-weighted first material texture; scale assumes nominal class height. Boundary loops are hole proxies, including intentional openings. Components welded per object at 1e-6 units.','textures':textures}

def render_setup(res):
    s=bpy.context.scene; s.render.engine='BLENDER_EEVEE' if 'BLENDER_EEVEE' in [x.identifier for x in s.render.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE_NEXT'; s.render.resolution_x=s.render.resolution_y=res; s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGBA'; s.render.film_transparent=True
    s.world.color=(.35,.35,.35); s.view_settings.view_transform='Standard'
    for loc,power,size in [((3,-4,4),450,5),((-3,-1,2),300,4),((0,3,3),400,4)]:
        bpy.ops.object.light_add(type='AREA',location=loc); o=bpy.context.object; o.data.energy=power; o.data.shape='DISK'; o.data.size=size; o.rotation_euler=(-o.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add(location=(0,-3.119,0)); cam=bpy.context.object; cam.data.type='PERSP'; cam.data.angle=math.radians(20); s.camera=cam
    return cam

def normalize():
    objs=meshes(); pts=[o.matrix_world@Vector(c) for o in objs for c in o.bound_box]; lo=Vector([min(p[i] for p in pts) for i in range(3)]); hi=Vector([max(p[i] for p in pts) for i in range(3)]); center=(lo+hi)*.5; factor=1/max(hi-lo)
    # Apply in world space without moving parent hierarchies multiple times.
    from mathutils import Matrix
    matrix=Matrix.Scale(factor,4)@Matrix.Translation(-center)
    worlds={o:o.matrix_world.copy() for o in objs}
    for o in objs: o.parent=None; o.matrix_world=matrix@worlds[o]

def turntable(cam,dest):
    dest.mkdir(parents=True,exist_ok=True)
    for i in range(8):
        a=i*math.pi/4; cam.location=(3.119*math.sin(a),-3.119*math.cos(a),0); cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler(); bpy.context.scene.render.filepath=str(dest/f'{i:02}.png'); bpy.ops.render.render(write_still=True)

def cleanup(budget):
    objs=meshes(); bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active=objs[0]; bpy.ops.object.join(); o=bpy.context.object
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bm=bmesh.new(); bm.from_mesh(o.data); bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6); bm.to_mesh(o.data); bm.free(); o.data.update()
    # Triangulation first makes the face target a triangle budget.
    mod=o.modifiers.new('triangulate','TRIANGULATE'); bpy.ops.object.modifier_apply(modifier=mod.name)
    for _ in range(5):
        n=len(o.data.polygons)
        if n<=budget: break
        mod=o.modifiers.new('Quest budget','DECIMATE'); mod.ratio=max(.001,(budget-2)/n); mod.use_collapse_triangulate=True; bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new(); bm.from_mesh(o.data)
    loose=[v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm,geom=loose,context='VERTS'); bm.to_mesh(o.data); bm.free(); o.data.update()
    return len(o.data.polygons)<=budget

def main():
    a=args(); out=pathlib.Path(a.output); out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.context.scene.world=bpy.data.worlds.new('Neutral')
    bpy.ops.import_scene.gltf(filepath=str(pathlib.Path(a.input).resolve()))
    if not meshes(): raise RuntimeError('No mesh in GLB')
    raw=metrics(a.height); normalize(); cam=render_setup(a.resolution); turntable(cam,out/'raw')
    fit=cleanup(a.budget); cleaned=metrics(a.height)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes(): o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out/'cleaned.glb'),export_format='GLB',use_selection=True)
    turntable(cam,out/'cleaned')
    (out/'metrics.json').write_text(json.dumps({'raw':raw,'cleaned':cleaned,'tri_budget':a.budget,'within_budget':fit,'cleanup':'weld at 1e-6, triangulate, iterative collapse decimation; UVs/materials retained; no manual repairs','blender_version':bpy.app.version_string,'clinical_accuracy':'unreviewed'},indent=2)+'\n')
if __name__=='__main__': main()
