## Детали реализации

Сборка приложения:
`docker compose build
`

Запуск приложения:
`docker compose up -d
`

После запуска приложения ждём готовности (30 сек) и импортируем конфигурацию LDAP:

`docker cp ldap/config.ldif bionicpro-openldap:/tmp/config.ldif`

`docker exec -i bionicpro-openldap ldapadd -x \
  -D "cn=admin,dc=example,dc=com" \
  -w "admin" \
  -f /tmp/config.ldif`

Вы должны увидеть вывод:

> adding new entry "ou=People,dc=example,dc=com"  
>   
> adding new entry "ou=Groups,dc=example,dc=com"  
>   
> adding new entry "uid=john.doe,ou=People,dc=example,dc=com"  
>   
> adding new entry "uid=jane.smith,ou=People,dc=example,dc=com"  
>   
> adding new entry "uid=alex,ou=People,dc=example,dc=com"  
>   
> adding new entry "cn=user,ou=Groups,dc=example,dc=com"  
>   
> adding new entry "cn=prothetic_user,ou=Groups,dc=example,dc=com"

