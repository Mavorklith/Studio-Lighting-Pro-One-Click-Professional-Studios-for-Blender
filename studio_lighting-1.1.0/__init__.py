# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {'name':'Studio Lighting','author':'Studio Lighting','version':(1,1,0),
           'blender':(4,2,0),'location':'View3D > Sidebar > Studio Lighting',
           'description':'50 lighting studios and 30 cameras for selected objects','category':'Lighting'}

import math
import random
from pathlib import Path
import bpy
import bpy.utils.previews
from mathutils import Vector, Quaternion
from bpy.props import EnumProperty, FloatProperty, IntProperty, BoolProperty, PointerProperty
from .presets import RECIPES, CAMERAS, PALETTES, direction
from . import sets

STUDIO_ITEMS = [(str(i),r[0],r[1]) for i,r in enumerate(RECIPES)]
CAMERA_ITEMS = [(str(i),r[0],r[0]) for i,r in enumerate(CAMERAS)]
PREVIEWS = None
GEOMETRY = {'MESH','CURVE','SURFACE','META','FONT'}

def collection(scene, name):
    c=bpy.data.collections.new(name); scene.collection.children.link(c); return c

def obj_new(c,name,data):
    o=bpy.data.objects.new(name,data); c.objects.link(o); return o

def aim(o,target):
    o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def clean(c):
    for o in list(c.objects):
        data=o.data; bpy.data.objects.remove(o,do_unlink=True)
        if data and data.users==0:
            if isinstance(data,bpy.types.Mesh): bpy.data.meshes.remove(data)
            elif isinstance(data,bpy.types.Light): bpy.data.lights.remove(data)
            elif isinstance(data,bpy.types.Camera): bpy.data.cameras.remove(data)

def bounds(objects):
    pts=[o.matrix_world @ Vector(p) for o in objects for p in o.bound_box]
    if not pts: raise ValueError('Select at least one visible mesh, text or curve object.')
    lo=Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    hi=Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    return lo,hi,pts

def subjects(scene): return scene.sl_settings.subjects

def material(scene):
    s=scene.sl_settings
    if not s.material: s.material=bpy.data.materials.new('SL • Seamless surface')
    m=s.material; m.use_nodes=True
    shader=m.node_tree.nodes.get('Principled BSDF')
    color=PALETTES[RECIPES[int(s.studio)][7]][2]
    if s.background=='WHITE': color=(.8,.8,.8)
    if s.background=='DARK': color=(.012,.012,.012)
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=s.roughness
    return m

def backdrop(scene,scale):
    s=scene.sl_settings
    if s.background=='NONE': return
    # A circular floor sweeping smoothly into a surrounding wall: no horizon seam,
    # including rear/side cameras. Radius scales with the entire selection.
    R=scale*7; curve=scale*3; z=-scale*.015
    profile=[(0,z),(R,z)]
    for j in range(1,25):
        t=j*math.pi/48
        profile.append((R+curve*math.sin(t),z+curve*(1-math.cos(t))))
    profile.append((R+curve,scale*30))
    n=128; verts=[]
    for r,h in profile:
        verts.extend((r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n),h) for i in range(n))
    faces=[]
    for j in range(len(profile)-1):
        for i in range(n):
            k=(i+1)%n; faces.append((j*n+i,(j+1)*n+i,(j+1)*n+k,j*n+k))
    mesh=bpy.data.meshes.new('SL cyclorama'); mesh.from_pydata(verts,[],faces); mesh.update()
    o=obj_new(s.rig,'SL • Infinity sweep',mesh); o.data.materials.append(material(scene))
    for p in mesh.polygons:p.use_smooth=True

def light(scene,name,pos,target,power,size,color,strip=False):
    s=scene.sl_settings; d=bpy.data.lights.new(name,'AREA')
    d.energy=power*s.power; d.color=color
    d.shape='RECTANGLE' if strip else 'DISK'; d.size=size
    if strip:d.size_y=size*.12
    o=obj_new(s.rig,name,d); o.location=pos; aim(o,target); return o

def build_rig(scene):
    s=scene.sl_settings; clean(s.rig)
    lo,hi,_=bounds(subjects(scene).objects); scale=max((hi-lo).length*.5,.001)
    target=(lo+hi)*.5
    name,tech,az,el,size,fill,rim,pal=RECIPES[int(s.studio)]
    warm,cool,_=PALETTES[pal]; az+=s.rotation
    def lamp(label,a,e,d,p,sz,col,strip=False):
        return light(scene,'SL • '+label,target+Vector(direction(a,e))*scale*d,target,
                     p*scale*scale,sz*scale*s.softness,col,strip)
    lamp('Key',az,el,4,1000,size*.35 if tech=='Gobo' else size,warm,tech=='Strip')
    lamp('Fill',s.rotation if tech=='Rim' else az+85,20 if tech!='Clamshell' else -15,3.2,1000*fill,size*.8,cool,tech=='Strip')
    lamp('Edge',az+35 if tech=='Rim' else az+165,45,3.5,1000*rim,max(.6,size*.45),cool,True)
    if tech in {'Cross','High key','Rim'}:
        lamp('Counter edge',az-35 if tech=='Rim' else az-140,30,4,650*rim,size*.65,warm,True)
    if tech=='Bounce': lamp('Ceiling bounce',0,89,3,550,6,(1,1,1))
    if tech=='Gobo':
        # Physical slats between key and subject cast a window-blind pattern.
        key=s.rig.objects.get('SL • Key'); axis=key.rotation_euler.to_matrix()
        center=target+(key.location-target)*.5
        for j in range(5):
            vs=[center+axis@Vector((x*scale,(j-2)*scale*.3+y*scale,0))
                for x,y in [(-1.8,-.06),(1.8,-.06),(1.8,.06),(-1.8,.06)]]
            m=bpy.data.meshes.new('SL slat'); m.from_pydata(vs,[],[(0,1,2,3)]);m.update()
            o=obj_new(s.rig,'SL • Shadow slat',m)
            o.visible_camera=False
    backdrop(scene,scale)
    mood={'Rim':.1,'Low key':.08,'Split':.35,'Gobo':.3}.get(tech,1)
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=s.ambient*mood
    scene.render.film_transparent=s.background=='NONE'
    scene['studio_lighting_recipe']=name
    apply_camera(scene)

def apply_camera(scene):
    s=scene.sl_settings; lo,hi,pts=bounds(subjects(scene).objects)
    target=(lo+hi)*.5; scale=max((hi-lo).length,.002)
    if not s.camera_object or s.camera_object.name not in scene.objects:
        s.camera_object=obj_new(s.cameras,'SL • Camera',bpy.data.cameras.new('SL Camera'))
    cam=s.camera_object; scene.camera=cam
    name,az,el,lens,margin,roll=CAMERAS[int(s.camera)]
    # Floor-level protection keeps a camera outside the cyclorama floor.
    outward=Vector(direction(az,el)); cam.location=target+outward*scale
    aim(cam,target)
    q=cam.rotation_euler.to_quaternion() @ Quaternion((0,0,1),math.radians(roll))
    cam.rotation_euler=q.to_euler(); cam.data.lens=lens
    cam.data.type='ORTHO' if s.orthographic else 'PERSP'
    cam.data.sensor_fit='HORIZONTAL'; cam.data.sensor_width=36
    aspect=(scene.render.resolution_x*scene.render.pixel_aspect_x)/(scene.render.resolution_y*scene.render.pixel_aspect_y)
    tx=18/lens; ty=tx/aspect
    local=[q.inverted()@(p-target) for p in pts]
    distance=max(max(abs(p.x)/tx,abs(p.y)/ty)*margin*s.framing+p.z for p in local)
    cam.location=target+outward*max(distance,scale*.1)
    cam.location.z=max(cam.location.z,scale*.02)
    if el<0: aim(cam,target)
    cam.data.ortho_scale=max(max(abs(p.x)*2,abs(p.y)*2*aspect) for p in local)*margin*s.framing
    cam.data.clip_start=max(scale*.0001,.00001);cam.data.clip_end=scale*1000
    cam.data.dof.use_dof=s.dof; cam.data.dof.focus_distance=(cam.location-target).length
    cam.data.dof.aperture_fstop=s.fstop
    scene['studio_lighting_camera']=name
    sets.build(scene,lo,hi,PALETTES[RECIPES[int(s.studio)][7]])

class SLSettings(bpy.types.PropertyGroup):
    studio: EnumProperty(name='Studio',items=STUDIO_ITEMS)
    camera: EnumProperty(name='Camera angle',items=CAMERA_ITEMS,default='1')
    power: FloatProperty(name='Light power',default=1,min=.01,max=20)
    softness: FloatProperty(name='Softbox scale',default=1,min=.15,max=4)
    rotation: FloatProperty(name='Rig rotation',default=0,min=-180,max=180,subtype='NONE')
    ambient: FloatProperty(name='Ambient fill',default=.08,min=0,max=2)
    roughness: FloatProperty(name='Floor roughness',default=.6,min=0,max=1)
    framing: FloatProperty(name='Frame breathing room',default=1,min=1,max=3)
    background: EnumProperty(name='Background',items=[('PRESET','Studio palette',''),('WHITE','Clean white',''),('DARK','Deep charcoal',''),('NONE','Transparent','')])
    set_style: EnumProperty(name='Set design',items=sets.SET_ITEMS,default='AUTO')
    set_scale: FloatProperty(name='Decoration scale',default=1,min=.25,max=2.5)
    set_distance: FloatProperty(name='Backdrop distance',default=1.8,min=1.5,max=5)
    set_rotation: FloatProperty(name='Set rotation',default=0,min=-180,max=180)
    set_seed: IntProperty(name='Set variation',default=0,min=0)
    set_objects: PointerProperty(type=bpy.types.Collection)
    orthographic: BoolProperty(name='Orthographic camera')
    dof: BoolProperty(name='Depth of field')
    fstop: FloatProperty(name='Aperture',default=8,min=1,max=64)
    seed: IntProperty(name='Variation seed',default=1,min=0)
    samples: IntProperty(name='Render samples',default=64,min=8,max=4096)
    subjects: PointerProperty(type=bpy.types.Collection)
    rig: PointerProperty(type=bpy.types.Collection)
    cameras: PointerProperty(type=bpy.types.Collection)
    camera_object: PointerProperty(type=bpy.types.Object)
    material: PointerProperty(type=bpy.types.Material)
    source: PointerProperty(type=bpy.types.Scene)

class SL_OT_create(bpy.types.Operator):
    """Copy selected geometry into a centered studio with lights, set and camera"""
    bl_idname='studio_lighting.create'; bl_label='Create Studio from Selection';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context): return context.mode=='OBJECT' and any(o.type in GEOMETRY for o in context.selected_objects)
    def execute(self,context):
        source=context.scene; settings=source.sl_settings
        selected=[o for o in context.selected_objects if o.type in GEOMETRY and not o.hide_render]
        if not selected:self.report({'WARNING'},'Select visible mesh, curve or text objects.');return {'CANCELLED'}
        graph=context.evaluated_depsgraph_get(); copies=[]
        try:
            for o in selected:
                mesh=bpy.data.meshes.new_from_object(o.evaluated_get(graph),depsgraph=graph)
                if not mesh.vertices: bpy.data.meshes.remove(mesh);continue
                copies.append((o,mesh))
            if not copies:raise ValueError('The selection has no renderable geometry.')
        except Exception as exc:
            for _,m in copies:bpy.data.meshes.remove(m)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        scene=bpy.data.scenes.new('Studio Lighting • '+RECIPES[int(settings.studio)][0]); s=scene.sl_settings
        for key in ('studio','camera','power','softness','rotation','ambient','roughness','framing','background','orthographic','dof','fstop','samples','set_style','set_scale','set_distance','set_rotation','set_seed'):
            setattr(s,key,getattr(settings,key))
        s.source=source; s.subjects=collection(scene,'SL • Subjects');s.rig=collection(scene,'SL • Lighting');s.cameras=collection(scene,'SL • Cameras')
        for original,mesh in copies:
            o=obj_new(s.subjects,original.name+' • Studio',mesh);o.matrix_world=original.matrix_world.copy()
        lo,hi,_=bounds(s.subjects.objects); offset=Vector(((lo.x+hi.x)*.5,(lo.y+hi.y)*.5,lo.z))
        for o in s.subjects.objects:o.location-=offset
        scene.world=bpy.data.worlds.new('SL • World');scene.world.use_nodes=True
        scene.render.engine='CYCLES';scene.cycles.samples=s.samples;scene.cycles.use_denoising=True
        scene.render.resolution_x=1600;scene.render.resolution_y=1600;scene.render.resolution_percentage=100
        scene.view_settings.view_transform='AgX';build_rig(scene)
        context.window.scene=scene
        for o in s.subjects.objects:o.select_set(True)
        context.view_layer.objects.active=next(iter(s.subjects.objects))
        self.report({'INFO'},'Studio created. Source objects preserved. Use numpad 0 for camera view.')
        return {'FINISHED'}

class SL_OT_update(bpy.types.Operator):
    """Rebuild the studio using the current lighting and backdrop controls"""
    bl_idname='studio_lighting.update';bl_label='Apply Studio';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,c):return bool(c.scene.sl_settings.subjects and c.scene.sl_settings.subjects.objects and c.scene.sl_settings.rig)
    def execute(self,c):build_rig(c.scene);c.scene.cycles.samples=c.scene.sl_settings.samples;return {'FINISHED'}

class SL_OT_camera(bpy.types.Operator):
    """Frame all studio subjects and apply the selected camera composition"""
    bl_idname='studio_lighting.camera';bl_label='Apply Camera';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,c):return SL_OT_update.poll(c)
    def execute(self,c):apply_camera(c.scene);return {'FINISHED'}

class SL_OT_variation(bpy.types.Operator):
    """Generate repeatable lighting from the variation seed"""
    bl_idname='studio_lighting.variation';bl_label='Generate Variation';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,c):return SL_OT_update.poll(c)
    def execute(self,c):
        s=c.scene.sl_settings;r=random.Random(s.seed);s.rotation=r.uniform(-180,180);s.softness=r.uniform(.5,1.8);s.power=r.uniform(.7,1.4)
        build_rig(c.scene);return {'FINISHED'}

class SL_OT_source(bpy.types.Operator):
    """Return to the original scene without changing its objects"""
    bl_idname='studio_lighting.source';bl_label='Return to Source Scene'
    @classmethod
    def poll(cls,c):return bool(c.scene.sl_settings.source)
    def execute(self,c):c.window.scene=c.scene.sl_settings.source;return {'FINISHED'}

class SL_OT_step(bpy.types.Operator):
    """Browse and apply the previous or next studio recipe"""
    bl_idname='studio_lighting.step';bl_label='Browse Studio';bl_options={'REGISTER','UNDO'}
    delta: IntProperty(default=1)
    def execute(self,c):
        s=c.scene.sl_settings;s.studio=str((int(s.studio)+self.delta)%50)
        if SL_OT_update.poll(c):build_rig(c.scene)
        return {'FINISHED'}

class SL_OT_reset(bpy.types.Operator):
    """Restore default light power, softness, rotation and ambient fill"""
    bl_idname='studio_lighting.reset';bl_label='Reset Light Shaping';bl_options={'REGISTER','UNDO'}
    def execute(self,c):
        s=c.scene.sl_settings
        for name in ('power','softness','rotation','ambient','roughness'):s.property_unset(name)
        if SL_OT_update.poll(c):build_rig(c.scene)
        return {'FINISHED'}

class SL_PT_panel(bpy.types.Panel):
    bl_label='Studio Lighting';bl_idname='SL_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Studio Lighting'
    def draw(self,context):
        l=self.layout;s=context.scene.sl_settings
        l.label(text='50 STUDIOS  /  30 CAMERAS',icon='LIGHT_AREA')
        if PREVIEWS and s.studio in PREVIEWS:l.template_icon(icon_value=PREVIEWS[s.studio].icon_id,scale=7)
        l.prop(s,'studio');l.label(text=RECIPES[int(s.studio)][1]+' lighting')
        row=l.row(align=True);row.operator('studio_lighting.step',text='Previous',icon='TRIA_LEFT').delta=-1
        row.operator('studio_lighting.step',text='Next',icon='TRIA_RIGHT').delta=1
        if not s.subjects:
            l.operator('studio_lighting.create',icon='ADD');l.label(text='Select objects in Object Mode.')
            l.prop(s,'camera');return
        l.operator('studio_lighting.update',icon='FILE_REFRESH')
        box=l.box();box.label(text='Light shaping')
        for k in ('power','softness','rotation','ambient'):box.prop(s,k)
        box.operator('studio_lighting.reset',icon='LOOP_BACK')
        box=l.box();box.label(text='Backdrop & set design',icon='OUTLINER_OB_MESH');box.prop(s,'background');box.prop(s,'set_style')
        if s.set_style!='NONE':
            for k in ('set_scale','set_distance','set_rotation','set_seed'):box.prop(s,k)
        box.prop(s,'roughness')
        box=l.box();box.label(text='Camera composition',icon='CAMERA_DATA')
        for k in ('camera','framing','orthographic','dof'):box.prop(s,k)
        if s.dof:box.prop(s,'fstop')
        box.operator('studio_lighting.camera')
        box=l.box();box.prop(s,'seed');box.operator('studio_lighting.variation',icon='SHADERFX')
        l.prop(s,'samples');l.label(text='Apply Studio to update settings.');l.operator('render.render',text='Render Image',icon='RENDER_STILL')
        l.operator('studio_lighting.source',icon='BACK')

CLASSES=(SLSettings,SL_OT_create,SL_OT_update,SL_OT_camera,SL_OT_variation,SL_OT_source,SL_OT_step,SL_OT_reset,SL_PT_panel)
def register():
    global PREVIEWS
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.sl_settings=PointerProperty(type=SLSettings)
    PREVIEWS=bpy.utils.previews.new()
    for i in range(50):
        path=Path(__file__).parent/'thumbnails'/f'{i:02d}.png'
        if path.exists():PREVIEWS.load(str(i),str(path),'IMAGE')
def unregister():
    global PREVIEWS
    if PREVIEWS:bpy.utils.previews.remove(PREVIEWS)
    PREVIEWS=None
    del bpy.types.Scene.sl_settings
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
