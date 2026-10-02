import type {MetadataRoute} from 'next';

export default function robots():MetadataRoute.Robots{return {
 rules:{userAgent:'*',allow:'/',disallow:['/login','/world','/overview','/infrastructure','/incidents','/agent','/deployments','/reports','/settings','/api/']},
 sitemap:'https://nightwatch.midhunpm.in/sitemap.xml',
 host:'https://nightwatch.midhunpm.in'
};}
