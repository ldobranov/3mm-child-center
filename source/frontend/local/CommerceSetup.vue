<script setup lang="ts">
import {onMounted,onUnmounted,ref,computed} from 'vue'
import {UiButton,UiField} from '@3mm/ui/v1'
import {useApplicationStrings} from './i18n'
import {useLocal} from './use-local'
import Status from './Status.vue'
type Settings={revision:number;time_article_id:number|null;unit:string;places:number[];articles:{article_id:number;label:string}[];default_place_id?:number|null;guardian_category_id?:number|null}
const strings=useApplicationStrings(),{t}=strings
const {allowed,access,can,read,readFailure,command,busy,pending,error,resolve,reviewed}=useLocal(strings)
const settings=ref<Settings|null>(null),loading=ref(false),query=ref(''),section=ref('articles'),offset=ref(0),more=ref(false)
const rows=ref<{article_id?:number;place_id?:number;category_id?:number;label:string}[]>([])
const baseline=ref(''),saved=ref(false)
const placeNames=ref<Record<number,string>>({})
const articleNames=ref<Record<number,string>>({})
const categoryNames=ref<Record<number,string>>({})
const placeLabel=(id:number)=>placeNames.value[id]||`${t('commerce_place')} #${id}`
const dirty=computed(()=>!!settings.value&&JSON.stringify(settings.value)!==baseline.value)
const locked=computed(()=>loading.value||busy.value||!!pending.value)
let disposed=false,serial=0
onUnmounted(()=>{disposed=true;serial++})
async function refresh(){
  const current=++serial;settings.value=null;rows.value=[];placeNames.value={};articleNames.value={};loading.value=true
  await access()
  try{if(!can('commerce_settings'))return
    const result=await read<Settings>('commerce_settings',{});if(!disposed&&current===serial){settings.value=result;baseline.value=JSON.stringify(result);saved.value=false}
    if(result.guardian_category_id&&can('barsy_categories')){
      const categories=await read<{status:string;items:{category_id:number;label:string}[]}>('barsy_categories',{offset:0,category_id:result.guardian_category_id})
      if(disposed||current!==serial)return
      if(categories.status==='ready')for(const category of categories.items)categoryNames.value[category.category_id]=category.label
    }
    if(disposed||current!==serial)return
    if(result.time_article_id&&can('barsy_articles')){
      const articles=await read<{status:string;items:{article_id:number;label:string}[]}>('barsy_articles',{query:'',offset:0,article_id:result.time_article_id})
      if(disposed||current!==serial)return
      if(articles.status==='ready')for(const article of articles.items)if(article.article_id===result.time_article_id)articleNames.value[article.article_id]=article.label
    }
    if(!result.places.length||!can('barsy_places'))return
    // At most 32 configured IDs: two bounded directory pages, never a full crawl.
    for(const start of [0,20]){
      const page=await read<{status:string;items:{place_id:number;label:string}[];has_more:boolean}>('barsy_places',{offset:start,place_ids:result.places})
      if(disposed||current!==serial)return
      if(page.status!=='ready')break
      for(const place of page.items)placeNames.value[place.place_id]=place.label
      if(!page.has_more)break
    }
  }catch(failure){if(!disposed&&current===serial)readFailure(failure)}
  finally{if(!disposed&&current===serial)loading.value=false}
}
async function catalog(start=0){
  if(locked.value)return
  offset.value=start;loading.value=true;rows.value=[];more.value=false;error.value=''
  const current=++serial
  try{
    const result=await read<{status:string;items:typeof rows.value;has_more:boolean}>('barsy_'+section.value,section.value==='articles'?{query:query.value,offset:start}:{offset:start})
    if(disposed||current!==serial)return
    if(result.status!=='ready'){error.value=result.status==='invalid_response'?'barsy_invalid_response':'barsy_unavailable';return}
    rows.value=result.items;more.value=result.has_more
    if(section.value==='places')for(const place of result.items)if(place.place_id)placeNames.value[place.place_id]=place.label
    if(section.value==='articles')for(const article of result.items)if(article.article_id)articleNames.value[article.article_id]=article.label
    if(section.value==='categories')for(const category of result.items)if(category.category_id)categoryNames.value[category.category_id]=category.label
  }catch(failure){if(!disposed&&current===serial)readFailure(failure)}
  finally{if(!disposed&&current===serial)loading.value=false}
}
async function save(){
  if(!settings.value||locked.value||!dirty.value)return
  const {revision,...value}=settings.value
  const result=await command('commerce_save_settings',{...value,expected_revision:revision})
  if(result&&!disposed){await refresh();if(!disposed&&settings.value)saved.value=true}
}
async function review(){await resolve();await refresh()}
function removePlace(id:number){if(settings.value){settings.value.places=settings.value.places.filter(p=>p!==id);if(settings.value.default_place_id===id)settings.value.default_place_id=null}}
onMounted(refresh)
</script>
<template>
  <section v-if="allowed.includes('commerce_settings')" class="ui-stack">
    <h2 id="commerce-configuration-title">{{t('commerce_configuration')}}</h2><p class="cc-muted">{{t('commerce_configuration_notice')}}</p>
    <Status :busy="busy" :pending="pending" :error="error" @resolve="review" @reviewed="reviewed();refresh()"/>
    <form v-if="settings" aria-labelledby="commerce-configuration-title" @submit.prevent="save"><fieldset class="cc-config-card" :disabled="locked">
      <div class="cc-config-time"><p>{{t('commerce_time_article')}}: <strong>{{settings.time_article_id?(articleNames[settings.time_article_id]||t('commerce_article_name_unavailable')):'—'}}</strong></p>
      <UiField id="commerce-unit" v-model="settings.unit" type="select" :label="t('commerce_time_unit')" :options="[{value:'hours',label:t('commerce_hours')},{value:'minutes',label:t('commerce_minutes')}]"/></div>
      <h3>{{t('commerce_places')}}</h3>
      <p v-if="!settings.places.length">—</p>
      <ul v-else class="cc-place-list">
        <li v-for="id in settings.places" :key="id">
          <UiButton variant="danger" type="button" :aria-label="t('remove')+' '+placeLabel(id)" :title="t('remove')+' '+placeLabel(id)" @click="removePlace(id)">{{placeLabel(id)}}</UiButton>
        </li>
      </ul>
      <UiField id="commerce-default-place" :model-value="settings.default_place_id?String(settings.default_place_id):''" type="select" :label="t('commerce_default_place')" :options="[{value:'',label:'—'},...settings.places.map(id=>({value:String(id),label:placeLabel(id)}))]" @update:model-value="settings.default_place_id=$event?Number($event):null"/>
      <p class="cc-muted">{{t('commerce_default_place_hint')}}</p>
      <p>{{t('commerce_guardian_category')}}: <strong>{{settings.guardian_category_id?(categoryNames[settings.guardian_category_id]||t('commerce_article_name_unavailable')):'—'}}</strong></p>
      <h3>{{t('commerce_consumption_articles')}}</h3>
      <div class="cc-article-choices"><UiButton v-for="a in settings.articles" :key="a.article_id" variant="danger" type="button" :aria-label="t('remove')+' '+a.label" :title="t('remove')+' '+a.label" @click="settings.articles=settings.articles.filter(p=>p.article_id!==a.article_id)">{{a.label}}</UiButton></div>
    </fieldset></form>
    <template v-if="settings">
      <h2>{{t('barsy_directory')}}</h2>
      <form @submit.prevent="catalog()"><fieldset class="cc-catalog-filter" :disabled="locked">
        <UiField id="commerce-catalog-type" v-model="section" type="select" :label="t('sections')" :options="[{value:'articles',label:t('barsy_articles')},{value:'places',label:t('barsy_places')},{value:'categories',label:t('commerce_categories')}]" @update:model-value="rows=[];offset=0;more=false"/>
        <UiField v-if="section==='articles'" id="commerce-catalog-search" v-model="query" :label="t('search')" :maxlength="120"/>
        <UiButton type="submit">{{t('barsy_load')}}</UiButton>
      </fieldset></form>
      <ul class="cc-catalog-list" :class="{'cc-catalog-places':section!=='articles'}"><li v-for="row in rows" :key="row.article_id||row.place_id||row.category_id">
        <span>{{row.label}}</span>
        <template v-if="row.article_id">
          <UiButton :aria-pressed="settings.time_article_id===row.article_id" :disabled="locked||settings.articles.some(a=>a.article_id===row.article_id)" @click="settings.time_article_id=row.article_id!">{{t(settings.time_article_id===row.article_id?'commerce_time_selected':'commerce_select_time')}}</UiButton>
          <UiButton variant="primary" :disabled="locked||settings.time_article_id===row.article_id||settings.articles.length>=32||settings.articles.some(a=>a.article_id===row.article_id)" @click="settings.articles.push({article_id:row.article_id!,label:row.label})">{{t('commerce_select_consumption')}}</UiButton>
        </template>
        <UiButton v-if="row.category_id" variant="primary" :disabled="locked||settings.guardian_category_id===row.category_id" @click="settings.guardian_category_id=row.category_id">{{t(settings.guardian_category_id===row.category_id?'commerce_category_selected':'commerce_select_category')}}</UiButton>
        <UiButton v-else-if="row.place_id" variant="primary" :disabled="locked||settings.places.length>=32||settings.places.includes(row.place_id!)" @click="settings.places.push(row.place_id!)">{{t('commerce_select_place')}}</UiButton>
      </li></ul>
      <div class="cc-toolbar"><UiButton :disabled="locked||offset===0" @click="catalog(Math.max(0,offset-(section==='articles'?50:20)))">{{t('previous')}}</UiButton><UiButton :disabled="locked||!more" @click="catalog(offset+(section==='articles'?50:20))">{{t('next')}}</UiButton></div>
      <aside class="cc-save-bar">
        <p role="status">{{t(dirty?'commerce_settings_unsaved':saved?'commerce_settings_saved':'commerce_settings_current')}}</p>
        <UiButton variant="primary" :disabled="locked||!dirty" @click="save">{{t('save_changes')}}</UiButton>
      </aside>
    </template>
  </section>
</template>
