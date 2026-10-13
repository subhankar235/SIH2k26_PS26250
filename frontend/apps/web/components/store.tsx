'use client';
import {createContext,useContext,useEffect,useState} from 'react';
import {initialRecords} from '@/lib/fixtures';
import {type Plan,experiment} from '@/lib/engine';
type State={records:typeof initialRecords;plan:Plan|null;previous:Plan|null;capacity:number;review:string;audit:string[];runs:ReturnType<typeof experiment>[]};
const initial:State={records:initialRecords,plan:null,previous:null,capacity:4,review:'Draft',audit:['Demo workspace initialized · synthetic-fixture-v1'],runs:[]};
const Context=createContext<{state:State;update:(fn:(s:State)=>State)=>void}>({state:initial,update:()=>{}});
export function Store({children}:{children:React.ReactNode}){const [state,setState]=useState(initial);const [ready,setReady]=useState(false);useEffect(()=>{try{const saved=localStorage.getItem('air-power-v1');if(saved){const parsed=JSON.parse(saved);if(Array.isArray(parsed.records)&&Array.isArray(parsed.audit)&&Array.isArray(parsed.runs))setState({...initial,...parsed});}}catch{}setReady(true)},[]);useEffect(()=>{if(ready)try{localStorage.setItem('air-power-v1',JSON.stringify(state))}catch{}},[state,ready]);return <Context.Provider value={{state,update:setState}}>{children}</Context.Provider>}
export const useStore=()=>useContext(Context);
