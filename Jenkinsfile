pipeline {
    agent any

    environment {
        // Git Configuration
        GIT_REPO         = "https://git.iirs.gov.in/trainee.aman/jaldrishti.git"
        GIT_CRED         = "webdev_access_cred"
        
        // Registry Configuration
        REGISTRY_URL     = "registry.iirs.gov.in"
        REGISTRY_PROJECT = "jaldrishti"
        REGISTRY_CRED    = "REGISTRY_CRED"
        
        // K3s Configuration
        K3S_NAMESPACE    = "jaldrishti-staging"
        K3S_KUBECONFIG   = "K3S_KUBECONFIG"
        K3S_DIR          = "k3s_staging"
        
        // Image Names
        FRONTEND_IMAGE   = "${REGISTRY_URL}/${REGISTRY_PROJECT}/frontend"
        BACKEND_IMAGE    = "${REGISTRY_URL}/${REGISTRY_PROJECT}/backend"
        GEOSERVER_IMAGE  = "${REGISTRY_URL}/${REGISTRY_PROJECT}/geoserver"
        OLLAMA_IMAGE     = "${REGISTRY_URL}/${REGISTRY_PROJECT}/ollama"
        MONGO_IMAGE      = "${REGISTRY_URL}/${REGISTRY_PROJECT}/mongo"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: '*/main']],
                    extensions: [[$class: 'SubmoduleOption', recursiveSubmodules: true, trackingSubmodules: true, parentCredentials: true]],
                    userRemoteConfigs: [[url: env.GIT_REPO, credentialsId: env.GIT_CRED]]
                ])
            }
        }

        stage('Read Version') {
            steps {
                script {
                    def props = readFile('VERSION').trim().split('\n').collectEntries { line ->
                        def parts = line.split('=')
                        [(parts[0].trim()): parts[1].trim()]
                    }
                    ['frontend', 'backend', 'geoserver', 'ollama', 'mongo'].each { svc ->
                        if (!props[svc]) error "VERSION missing entry for: ${svc}"
                    }
                
                    env.FRONTEND_VERSION  = props.frontend
                    env.BACKEND_VERSION   = props.backend
                    env.GEOSERVER_VERSION = props.geoserver
                    env.OLLAMA_VERSION    = props.ollama
                    env.MONGO_VERSION     = props.mongo
                    
                    // Full image tags with version
                
                    env.FRONTEND_FULL  = "${env.FRONTEND_IMAGE}:${props.frontend}"
                    env.BACKEND_FULL   = "${env.BACKEND_IMAGE}:${props.backend}"
                    env.GEOSERVER_FULL = "${env.GEOSERVER_IMAGE}:${props.geoserver}"
                    env.OLLAMA_FULL    = "${env.OLLAMA_IMAGE}:${props.ollama}"
                    env.MONGO_FULL     = "${env.MONGO_IMAGE}:${props.mongo}"
                    
                    echo "Versions: frontend=${env.FRONTEND_VERSION} backend=${env.BACKEND_VERSION} geoserver=${env.GEOSERVER_VERSION} ollama=${env.OLLAMA_VERSION} mongo=${env.MONGO_VERSION}"
                }
            }
        }

        stage('Determine Run Mode') {
            steps {
                script {
                    withCredentials([
                        usernamePassword(credentialsId: env.REGISTRY_CRED, usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS'),
                        file(credentialsId: env.K3S_KUBECONFIG, variable: 'KUBECONFIG')
                    ]) {
                        def auth = sh(script: "echo -n \"\${REG_USER}:\${REG_PASS}\" | base64", returnStdout: true).trim()

                        // Check if image exists in Harbor registry
                        def harborHasTag = { repo, tag ->
                            def code = sh(
                                script: """curl -sk -o /dev/null -w "%{http_code}" \
                                    -H "Authorization: Basic ${auth}" \
                                    "https://${env.REGISTRY_URL}/api/v2.0/projects/${env.REGISTRY_PROJECT}/repositories/${repo}/artifacts/${tag}" """,
                                returnStdout: true
                            ).trim()
                            code == '200'
                        }

                        // Get current image tag running in K3s
                        def k3sImageTag = { resource, kind ->
                            def img = sh(
                                script: "kubectl get ${kind} ${resource} -n ${env.K3S_NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo ''",
                                returnStdout: true
                            ).trim()
                            img.contains(':') ? img.tokenize(':').last() : ''
                        }

                        def svcDefs = [
                            [name: 'frontend',  repo: 'frontend',  tag: env.FRONTEND_VERSION,  k3sTag: k3sImageTag('frontend', 'deployment')],
                            [name: 'backend',   repo: 'backend',   tag: env.BACKEND_VERSION,   k3sTag: k3sImageTag('backend', 'deployment')],
                            [name: 'geoserver', repo: 'geoserver', tag: env.GEOSERVER_VERSION, k3sTag: k3sImageTag('geoserver', 'deployment')],
                            [name: 'ollama',    repo: 'ollama',    tag: env.OLLAMA_VERSION,    k3sTag: k3sImageTag('ollama', 'deployment')],
                            [name: 'mongo',     repo: 'mongo',     tag: env.MONGO_VERSION,     k3sTag: k3sImageTag('mongo', 'statefulset')],
                        ]

                        def toVer = { t -> t ? t.replaceAll('^v', '').tokenize('.').collect { it.toInteger() } : [0, 0, 0] }
                        def gt    = { a, b -> a[0] != b[0] ? a[0] > b[0] : a[1] != b[1] ? a[1] > b[1] : a[2] > b[2] }

                        def anyBuild    = false
                        def anyRedeploy = false
                        def anyRollback = false

                        svcDefs.each { svc ->
                            def inHarbor = harborHasTag(svc.repo, svc.tag)
                            def action
                            if (!inHarbor) {
                                action = 'build'
                                anyBuild = true
                            } else if (svc.tag == svc.k3sTag) {
                                action = 'skip'
                            } else if (!svc.k3sTag || gt(toVer(svc.tag), toVer(svc.k3sTag))) {
                                action = 'redeploy'
                                anyRedeploy = true
                            } else {
                                action = 'rollback'
                                anyRollback = true
                            }
                            
                            // Set environment variables for each service action
                            env["${svc.name.toUpperCase()}_ACTION"] = action
                            echo "${svc.name}: tag=${svc.tag} harbor=${inHarbor} k3s=${svc.k3sTag ?: 'none'} -> ${action}"
                        }

                        // Check what files changed
                        def changedFiles = currentBuild.changeSets
                            .collectMany { cs -> cs.items.collectMany { entry -> entry.affectedFiles.collect { it.path } } }
                            .unique()
                            .join('\n')
                        if (!changedFiles.trim()) changedFiles = 'all'
                        def onlyK3sChanged = changedFiles.split('\n').every { it.startsWith('k8s/') }

                        if (anyBuild) {
                            env.RUN_MODE = 'full-build'
                        } else if (anyRollback && !anyRedeploy) {
                            env.RUN_MODE = 'rollback'
                        } else if (anyRedeploy) {
                            env.RUN_MODE = 'redeploy-only'
                        } else if (onlyK3sChanged) {
                            env.RUN_MODE = 'config-only'
                        } else {
                            currentBuild.result = 'ABORTED'
                            error """No actionable changes detected.
  Actions:  frontend=${env.FRONTEND_ACTION} backend=${env.BACKEND_ACTION} geoserver=${env.GEOSERVER_ACTION} ollama=${env.OLLAMA_ACTION} mongo=${env.MONGO_ACTION}
  Changed files:\n${changedFiles}"""
                        }
                        echo "Run mode: ${env.RUN_MODE}"
                    }
                }
            }
        }

        stage('Build Images') {
            when { expression { env.RUN_MODE == 'full-build' } }
            parallel {
                stage('Frontend') {
                    steps {
                        script {
                            if (env.FRONTEND_ACTION == 'build') {
                                sh """
                                    docker build --no-cache \
                                      --target prod \
                                      -t ${env.FRONTEND_FULL} \
                                      ./frontend
                                """
                            } else {
                                echo "Skipping frontend build (action: ${env.FRONTEND_ACTION})"
                            }
                        }
                    }
                }
                stage('Backend') {
                    steps {
                        script {
                            if (env.BACKEND_ACTION == 'build') {
                                sh """
                                    docker build --no-cache \
                                      -t ${env.BACKEND_FULL} \
                                      ./backend
                                """
                            } else {
                                echo "Skipping backend build (action: ${env.BACKEND_ACTION})"
                            }
                        }
                    }
                }
                stage('GeoServer') {
                    steps {
                        script {
                            if (env.GEOSERVER_ACTION == 'build') {
                                sh """
                                    docker build --no-cache \
                                      -t ${env.GEOSERVER_FULL} \
                                      ./geoserver
                                """
                            } else {
                                echo "Skipping geoserver build (action: ${env.GEOSERVER_ACTION})"
                            }
                        }
                    }
                }
                stage('Ollama') {
                    steps {
                        script {
                            if (env.OLLAMA_ACTION == 'build') {
                                sh """
                                    docker pull ollama/ollama:latest
                                    docker tag ollama/ollama:latest ${env.OLLAMA_FULL}
                                """
                            } else {
                                echo "Skipping ollama pull (action: ${env.OLLAMA_ACTION})"
                            }
                        }
                    }
                }
                stage('MongoDB') {
                    steps {
                        script {
                            if (env.MONGO_ACTION == 'build') {
                                sh """
                                    docker pull mongo:7
                                    docker tag mongo:7 ${env.MONGO_FULL}
                                """
                            } else {
                                echo "Skipping mongo pull (action: ${env.MONGO_ACTION})"
                            }
                        }
                    }
                }
            }
        }

        stage('Push to Registry') {
            when { expression { env.RUN_MODE == 'full-build' } }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: env.REGISTRY_CRED,
                    usernameVariable: 'REG_USER',
                    passwordVariable: 'REG_PASS'
                )]) {
                    script {
                        sh "echo \"\${REG_PASS}\" | docker login ${env.REGISTRY_URL} -u \"\${REG_USER}\" --password-stdin"

                        // Push images based on build actions
                        def services = [
                           
                            [name: 'frontend', image: env.FRONTEND_FULL, action: env.FRONTEND_ACTION],
                            [name: 'backend', image: env.BACKEND_FULL, action: env.BACKEND_ACTION],
                            [name: 'geoserver', image: env.GEOSERVER_FULL, action: env.GEOSERVER_ACTION],
                            [name: 'ollama', image: env.OLLAMA_FULL, action: env.OLLAMA_ACTION],
                            [name: 'mongo', image: env.MONGO_FULL, action: env.MONGO_ACTION],
                        ]
                        
                        services.each { svc ->
                            if (svc.action == 'build') {
                                sh "docker push ${svc.image}"
                                // Also push as latest
                                def latestImage = svc.image.replaceAll(':[^:]*$', ':latest')
                                sh "docker tag ${svc.image} ${latestImage} && docker push ${latestImage}"
                            }
                        }

                        sh "docker logout ${env.REGISTRY_URL}"
                    }
                }
            }
        }

        stage('Deploy to K3s') {
            steps {
                withCredentials([
                    file(credentialsId: env.K3S_KUBECONFIG, variable: 'KUBECONFIG'),
                    usernamePassword(
                        credentialsId: env.REGISTRY_CRED,
                        usernameVariable: 'REG_USER',
                        passwordVariable: 'REG_PASS'
                    )
                ]) {
                    script {
                        // Create namespace
                        sh "kubectl apply -f ${env.K3S_DIR}/namespace.yaml"

                        // Create image pull secret
                        sh """
                            kubectl create secret docker-registry harbor-pull-secret \
                              --docker-server=${env.REGISTRY_URL} \
                              --docker-username="\${REG_USER}" \
                              --docker-password="\${REG_PASS}" \
                              --namespace=${env.K3S_NAMESPACE} \
                              --dry-run=client -o yaml | kubectl apply -f -
                        """

                        // Apply ConfigMaps and Secrets
                        sh """
                            kubectl apply -f ${env.K3S_DIR}/configmap.yaml
                            kubectl apply -f ${env.K3S_DIR}/secret.yaml
                        """

                        // Apply PersistentVolumeClaims
                        sh """
                            kubectl apply -f ${env.K3S_DIR}/mongodb/pvc.yaml
                            kubectl apply -f ${env.K3S_DIR}/backend/pvc.yaml
                            kubectl apply -f ${env.K3S_DIR}/geoserver/pvc.yaml
                            kubectl apply -f ${env.K3S_DIR}/ollama/pvc.yaml
                        """

                        // Config-only: restart deployments to pick up new config
                        if (env.RUN_MODE == 'config-only') {
                            sh """
                                
                                kubectl rollout restart deployment/frontend -n ${env.K3S_NAMESPACE}
                                kubectl rollout restart deployment/backend -n ${env.K3S_NAMESPACE}
                                kubectl rollout restart deployment/geoserver -n ${env.K3S_NAMESPACE}
                                kubectl rollout restart deployment/ollama -n ${env.K3S_NAMESPACE}
                            """
                        }

                        // Deploy MongoDB (StatefulSet)
                        sh """
                            cp ${env.K3S_DIR}/mongodb/deployment.yaml /tmp/mongo-resolved.yaml
                            sed -i 's|image: mongo:7|image: ${env.MONGO_FULL}|g' /tmp/mongo-resolved.yaml
                            kubectl apply -f /tmp/mongo-resolved.yaml
                            kubectl apply -f ${env.K3S_DIR}/mongodb/service.yaml
                        """

                        // Deploy services with image substitution
                        def services = [
                           
                            [file: 'frontend/deployment', placeholder: 'FRONTEND_IMAGE_PLACEHOLDER', image: env.FRONTEND_FULL],
                            [file: 'backend/deployment', placeholder: 'BACKEND_IMAGE_PLACEHOLDER', image: env.BACKEND_FULL],
                            [file: 'geoserver/deployment', placeholder: 'iirs-geoserver', image: env.GEOSERVER_FULL],
                            [file: 'ollama/deployment', placeholder: 'ollama/ollama:latest', image: env.OLLAMA_FULL],
                        ]
                        
                        services.each { svc ->
                            sh """
                                cp ${env.K3S_DIR}/${svc.file}.yaml /tmp/${svc.file}-resolved.yaml
                                sed -i 's|${svc.placeholder}|${svc.image}|g' /tmp/${svc.file}-resolved.yaml
                                kubectl apply -f /tmp/${svc.file}-resolved.yaml
                            """
                        }

                        // Apply services
                        sh """
                            
                            kubectl apply -f ${env.K3S_DIR}/frontend/service.yaml
                            kubectl apply -f ${env.K3S_DIR}/backend/service.yaml
                            kubectl apply -f ${env.K3S_DIR}/geoserver/service.yaml
                            kubectl apply -f ${env.K3S_DIR}/ollama/service.yaml
                        """

                        // Apply HPA if enabled
                        sh """
                            kubectl apply -f ${env.K3S_DIR}/frontend/hpa.yaml
                            kubectl apply -f ${env.K3S_DIR}/backend/hpa.yaml
                        """

                        // Apply Ingress
                        sh """
                            kubectl apply -f ${env.K3S_DIR}/ingress/ingress.yaml
                        """

                        // Show deployment status
                        sh "kubectl get pods -n ${env.K3S_NAMESPACE}"
                    }
                }
            }
        }

        stage('Verify Rollout') {
            when { expression { env.RUN_MODE in ['full-build', 'redeploy-only', 'rollback', 'config-only'] } }
            steps {
                withCredentials([file(credentialsId: env.K3S_KUBECONFIG, variable: 'KUBECONFIG')]) {
                    script {
                        def deployments = ['frontend', 'backend', 'geoserver', 'ollama']
                        def statefulsets = ['mongo']
                        
                        deployments.each { deploy ->
                            sh """
                                kubectl rollout status deployment/${deploy} -n ${env.K3S_NAMESPACE} --timeout=300s
                            """
                        }
                        
                        statefulsets.each { sts ->
                            sh """
                                kubectl rollout status statefulset/${sts} -n ${env.K3S_NAMESPACE} --timeout=300s
                            """
                        }
                        
                        sh "echo '' && kubectl get pods -n ${env.K3S_NAMESPACE}"
                        sh "echo '' && kubectl get services -n ${env.K3S_NAMESPACE}"
                        sh "echo '' && kubectl get ingress -n ${env.K3S_NAMESPACE}"
                    }
                }
            }
        }

        stage('Health Check') {
            when { expression { env.RUN_MODE in ['full-build', 'redeploy-only', 'rollback'] } }
            steps {
                script {
                    // Test each service endpoint
                    def services = [
                        'frontend': '/',
                        'backend': '/health',
                        'geoserver': '/geoserver/web/',
                        
                    ]
                    
                    services.each { name, path ->
                        sh """
                            echo "Testing ${name} at ${path}..."
                            kubectl run test-${name} --rm -i --restart=Never --image=busybox -n ${env.K3S_NAMESPACE} -- \
                              wget -q -O- http://${name}:80${path} || echo "WARNING: ${name} health check failed"
                        """
                    }
                }
            }
        }
    }

    post {
        success {
            echo "[${env.RUN_MODE}] Jaldrishti deployed to ${env.K3S_NAMESPACE} — frontend:${env.FRONTEND_VERSION} backend:${env.BACKEND_VERSION} geoserver:${env.GEOSERVER_VERSION} ollama:${env.OLLAMA_VERSION} mongo:${env.MONGO_VERSION}"
        }
        failure {
            script {
                // Rollback on failure
                if (env.RUN_MODE in ['full-build', 'redeploy-only', 'config-only']) {
                    withCredentials([file(credentialsId: env.K3S_KUBECONFIG, variable: 'KUBECONFIG')]) {
                        sh """
                            echo "Rolling back failed deployments..."
                            kubectl rollout undo deployment/frontend  -n ${env.K3S_NAMESPACE} || true
                            kubectl rollout undo deployment/backend   -n ${env.K3S_NAMESPACE} || true
                            kubectl rollout undo deployment/geoserver -n ${env.K3S_NAMESPACE} || true
                            kubectl rollout undo deployment/ollama    -n ${env.K3S_NAMESPACE} || true
                            kubectl rollout undo statefulset/mongo    -n ${env.K3S_NAMESPACE} || true
                            echo "Rollback completed. Check cluster status."
                        """
                    }
                }
                echo "Pipeline failed. Mode: ${env.RUN_MODE ?: 'unknown'}"
            }
        }
        always {
            script {
                // Cleanup test pods
                sh """
                    kubectl delete pods -n ${env.K3S_NAMESPACE} -l 'test-runner=true' || true
                """
            }
        }
    }
}