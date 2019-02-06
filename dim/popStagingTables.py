debug=False

import sys
if all([len(sys.argv)<2, debug==False]):
	sys.exit('PID not provided... ')
elif debug:
	pid=-1
else:
	pid=int(sys.argv[1])

from dimlib import *

r.init(include_webui=False)
csize,eaeSchema,uri=dwCNX(tinyset=True)
tracker=pdf([],columns=['status','instancecode','collection','timestarted','timefinished','chunkstart','chunkfinish','rowversion'])
objFrame=[]

def recordRowVersions():
	global tracker
	if tracker.empty:
		print('Tracker is Empty ')
		issue=True
	else:
		pgx=pgcnx(uri)
		tracker['pid']=pid
		tracker['instancetype']='mssql'
		tracker.fillna(-1,inplace=True)
		tracker[['status','instancecode','collection','chunkstart','chunkfinish','rowversion','pid']].to_sql('chunktraces',pgx,if_exists='append',index=False,schema='framework')
		tracker.drop(['chunkstart','chunkfinish'],axis=1,inplace=True)
		ixx=tracker.groupby(['instancecode','collection'],sort=False)['rowversion'].transform(max)==tracker['rowversion']
		tracker[ixx].to_sql('collectiontracker',pgx,if_exists='append',index=False,schema='framework')
		del tracker
		pgx.dispose()
		issue=False
	return issue

mssql_dict=objects_mssql(uri)
insList=mssql_dict['insList']
colFrame=mssql_dict['frame']

def copyCollectionShape(icode,cnxStr,uri):
	pgx=pgcnx(uri)
	sqx=sqlCnx(cnxStr)
	session=sessionmaker(bind=pgx)
	nuSession=session()
	nuSession.execute(''' TRUNCATE TABLE framework.tabshape ''')
	nuSession.commit()
	nuSession.close()
	dbQL="SELECT '" +icode+ "' as instancecode,COLUMN_NAME as column_str,DATA_TYPE as datatype,TABLE_NAME as collection FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_NAME DESC"
	dbShape=rsq(dbQL,sqx)
	dbShape['collection']=dbShape['collection'].str.lower()
	dbShape['column_str']=dbShape['column_str'].str.lower()
	dbShape.to_sql('tabshape',pgx,if_exists='append',index=False,schema='framework')
	sqx.close()
	pgx.dispose()
	del dbShape
	return None

@r.remote
def createCollections(sql_table,stage_table,schema_name,uri):
	pgx=pgcnx(uri)
	ddql=alchemyText(" SELECT framework.createcollection(:f_srcTab,:f_dstTab,:f_schema) ")
	ddql=" SELECT framework.createcollection('" +sql_table+ "','" +stage_table+ "','" +schema_name+ "')"
	session=sessionmaker(bind=pgx)
	nuSession=session()
	nuSession.execute(ddql)
	nuSession.commit()
	nuSession.close()
	pgx.dispose()
	return None

@r.remote
def popCollections(icode,connexion,iFrame):
	pgx=pgcnx(uri)
	trk=pdf([],columns=['collection','chunkstart','chunkfinish','rowversion','status','timestarted','timefinished'])
	try:
		sqx=sqlCnx(connexion)
	except podbc.Error as err:
		print('Error Connecting to ' +icode+ ' instance. See Error Logs for more details. ')
		logError(pid,'popStagingTables',err,uri)
		return trk
	chunk=pdf([],columns=['model'])
	for idx,rowdata in iFrame.iterrows():
		astart=dtm.utcnow()
		noChange=True
		rco=rowdata['collection']
		s_table=rowdata['s_table']
		scols=rowdata['stg_cols']
		rower=str(int(rowdata['rower']))
		sql="SELECT '" +icode+ "' as instancecode," +scols+ ",CONVERT(BIGINT,sys_ROWVERSION) AS ROWER FROM " +rco+ "(NOLOCK) WHERE CONVERT(BIGINT,sys_ROWVERSION) > " +rower
		for chunk in rsq(sql,sqx,chunksize=csize):
			cstart=dtm.utcnow()
			chunk.to_sql(s_table,pgx,if_exists='append',index=False,schema=eaeSchema)
			trk=trk.append({'status':False,'collection':rco,'rowversion':chunk['rower'].max(),'chunkfinish':dtm.utcnow(),'chunkstart':cstart},ignore_index=True)
			noChange=False
		trk.loc[(trk['collection']==rco),['status']]=True
		trk.loc[(trk['collection']==rco),['timefinished']]=dtm.utcnow()
		trk.loc[(trk['collection']==rco),['timestarted']]=astart
		if noChange:
			utnow=dtm.utcnow()
			trk=trk.append({'collection':rco,'rowversion':rower,'chunkfinish':utnow,'chunkstart':utnow,'status':True,'timestarted':astart,'timefinished':utnow},ignore_index=True)
	del chunk
	sqx.close()
	pgx.dispose()
	trk['instancecode']=icode
	return trk

print('Active Instances Found: ' +str(len(insList)))
if all([debug==False,len(insList)>0]):
	oneINS=insList[0]
	copyCollectionShape(oneINS['icode'],oneINS['sqlConStr'],uri)
	print('Table Shape copied... ')
	oneFrame=colFrame.loc[(colFrame['icode']==oneINS['icode']) & (colFrame['instancetype']=='mssql'),['collection','s_table']]
	collectionZIP=list(zip(oneFrame['collection'],oneFrame['s_table']))
	for iZIP in collectionZIP:
		iSQL_Tab,iStage_Tab=iZIP
		objFrame.append(createCollections.remote(iSQL_Tab,iStage_Tab,eaeSchema,uri))
	r.wait(objFrame)
	objFrame.clear()
	print('Staging Tables created... ')
	for ins in insList:
		cnxStr=ins['sqlConStr']
		instancecode=ins['icode']
		iFrame=colFrame.loc[(colFrame['icode']==instancecode) & (colFrame['instancetype']=='mssql'),['collection','s_table','rower','stg_cols']]
		objFrame.append(popCollections.remote(instancecode,cnxStr,iFrame))
	r.wait(objFrame)
	for obj in objFrame:
		tracker=tracker.append(r.get(obj),sort=False,ignore_index=True)
	del objFrame
	r.shutdown()
	print(tracker)
	recordRowVersions()
elif debug:
	print('Ready to DEBUG... ')
else:
	print('No Active Instances Found.')
