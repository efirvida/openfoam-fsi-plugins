/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright held by original author(s)
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of turbinesFoam, which is based on OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

\*---------------------------------------------------------------------------*/

#include "surfaceSamplerBase.H"
#include "volFields.H"
#include "dimensionedScalar.H"
#include "mathematicalConstants.H"
#include "OSspecific.H"
#include "PstreamReduceOps.H"
#include "PrimitivePatch.H"
#include "OFstream.H"

// * * * * * * * * * * * * * Private Member Functions  * * * * * * * * * * * //

void Foam::fv::surfaceSamplerBase::createBodyFrame
(
    const dictionary& dict
)
{
    const vector axis = dict.lookupOrDefault("bodyAxis", vector(1, 0, 0));

    if (mag(axis) < SMALL)
    {
        FatalErrorInFunction
            << "The 'bodyAxis' entry must be non-zero" << nl
            << exit(FatalError);
    }

    // Body axis e1 is the surface body axis expressed in the global frame;
    // complete the orthonormal basis deterministically
    const vector e1 = axis/mag(axis);

    vector e2 = e1 ^ vector(0, 0, 1);
    if (mag(e2) < SMALL)
    {
        e2 = e1 ^ vector(0, 1, 0);
    }
    e2 /= mag(e2);

    const vector e3 = e1 ^ e2;

    // Columns of bodyToGlobal_ are the body axes expressed in the global frame
    bodyToGlobal_ = tensor
    (
        e1.x(), e2.x(), e3.x(),
        e1.y(), e2.y(), e3.y(),
        e1.z(), e2.z(), e3.z()
    );

    identityBodyFrame_ = (bodyOrigin_ == vector::zero)
                      && (e1 == vector(1, 0, 0));

    if (identityBodyFrame_)
    {
        positionsBody_ = positions_;
        normalsBody_ = normals_;
    }
    else
    {
        const tensor globalToBody = bodyToGlobal_.T();

        forAll(positions_, i)
        {
            positionsBody_[i] = globalToBody & (positions_[i] - bodyOrigin_);
            normalsBody_[i] = globalToBody & normals_[i];
        }
    }
}


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

Foam::fv::surfaceSamplerBase::surfaceSamplerBase
(
    const dictionary& dict,
    const fvMesh& mesh,
    const word& geometryKey
)
:
    mesh_(mesh),
    surface_(),
    positions_(),
    normals_(),
    areas_(),
    positionsBody_(),
    normalsBody_(),
    bodyOrigin_(dict.lookupOrDefault("bodyOrigin", vector::zero)),
    bodyToGlobal_(tensor::I),
    identityBodyFrame_(true),
    rhoRef_(dict.lookupOrDefault<scalar>("rho", 1.0)),
    fsiActive_(false),
    fsiCoordFieldName_(word::null),
    fsiForceFieldName_(word::null),
    fsiDispFieldName_(word::null),
    fsiCoordFileName_(fileName::null),
    fsiCoordFieldPtr_(),
    fsiForceFieldPtr_(),
    fsiDispFieldPtr_(),
    fsiReferencePoints_(),
    fsiReferenceCentroids_(),
    fsiRotationPoint_(vector::zero),
    fsiRotationAxis_(vector(0, 0, 1)),
    fsiTotalAngle_(0.0),
    fsiGeometryInitialized_(false)
{
    if (!dict.found(geometryKey))
    {
        FatalErrorInFunction
            << "The surface sampler requires a '" << geometryKey << "' entry "
            << "giving the surface triangulation file" << nl
            << exit(FatalError);
    }

    fileName geometryPath = dict.get<fileName>(geometryKey);

    if (!isFile(geometryPath))
    {
        // Also accept a path relative to the case directory
        const fileName casePath = mesh_.time().path()/geometryPath;

        if (isFile(casePath))
        {
            geometryPath = casePath;
        }
    }

    if (!isFile(geometryPath))
    {
        FatalErrorInFunction
            << "Surface file " << geometryPath << " not found" << nl
            << exit(FatalError);
    }

    // MeshedSurface<face>::New auto-detects the format from the file
    // extension (STL, OBJ, VTK, ...) and keeps mixed tri/quad/poly faces
    surface_.reset(MeshedSurface<face>::New(geometryPath));

    if (surface_->size() == 0)
    {
        FatalErrorInFunction
            << "Surface file " << geometryPath
            << " contains no faces" << nl
            << exit(FatalError);
    }

    // One node per face: centroid position, outward unit normal, area
    positions_ = surface_->faceCentres();
    normals_ = surface_->faceNormals();
    areas_ = surface_->magFaceAreas();

    positionsBody_.setSize(positions_.size());
    normalsBody_.setSize(normals_.size());

    createBodyFrame(dict);

    // Optional FSI coupling layer: registry fields for the preCICE adapter
    createFsiFields(dict);

    Info<< "Surface sampler: read " << positions_.size()
        << " faces and " << surface_->points().size()
        << " vertices from " << geometryPath << endl;
}


void Foam::fv::surfaceSamplerBase::updateBodyFrame()
{
    if (identityBodyFrame_)
    {
        positionsBody_ = positions_;
        normalsBody_ = normals_;
        return;
    }

    const tensor globalToBody = bodyToGlobal_.T();

    forAll(positions_, i)
    {
        positionsBody_[i] = globalToBody & (positions_[i] - bodyOrigin_);
        normalsBody_[i] = globalToBody & normals_[i];
    }
}


void Foam::fv::surfaceSamplerBase::createFsiFields(const dictionary& dict)
{
    const dictionary& fsiDict = dict.subOrEmptyDict("fsi");

    if (fsiDict.empty())
    {
        return;
    }

    fsiActive_ = true;

    fsiCoordFieldName_ =
        fsiDict.getOrDefault<word>("coordinateField", "surfaceCoords");
    fsiForceFieldName_ =
        fsiDict.getOrDefault<word>("forceField", "surfaceForces");
    fsiDispFieldName_ =
        fsiDict.getOrDefault<word>("displacementField", "surfaceDisplacement");
    fsiCoordFileName_ =
        fsiDict.getOrDefault<fileName>("coordinateFile", fileName::null);

    const Time& runTime = mesh_.time();

    const label nPts = surfacePoints().size();

    // Surface vertices (global frame): the preCICE point cloud. In-memory
    // only (NO_READ/NO_WRITE); the adapter binds to it by name in the registry
    fsiCoordFieldPtr_.reset
    (
        new vectorIOField
        (
            IOobject
            (
                fsiCoordFieldName_,
                runTime.timeName(),
                runTime,
                IOobject::NO_READ,
                IOobject::NO_WRITE
            ),
            surfacePoints()
        )
    );

    // Per-vertex forces and displacements, zero-initialised; written/read by
    // the sampler and the adapter through the registry
    const Field<vector> zeroVecs(nPts, vector::zero);

    fsiForceFieldPtr_.reset
    (
        new vectorIOField
        (
            IOobject
            (
                fsiForceFieldName_,
                runTime.timeName(),
                runTime,
                IOobject::NO_READ,
                IOobject::NO_WRITE
            ),
            zeroVecs
        )
    );

    fsiDispFieldPtr_.reset
    (
        new vectorIOField
        (
            IOobject
            (
                fsiDispFieldName_,
                runTime.timeName(),
                runTime,
                IOobject::NO_READ,
                IOobject::NO_WRITE
            ),
            zeroVecs
        )
    );

    Info<< "Surface sampler: FSI coupling active (" << nPts << " vertices)"
        << nl
        << "    coordinate field   : " << fsiCoordFieldName_ << nl
        << "    force field        : " << fsiForceFieldName_ << nl
        << "    displacement field : " << fsiDispFieldName_ << endl;
}


void Foam::fv::surfaceSamplerBase::writeCoordinateField()
{
    if (!fsiActive_)
    {
        return;
    }

    // Assign the current surface vertices (global frame) to the registry field
    *fsiCoordFieldPtr_ = surfacePoints();
}


void Foam::fv::surfaceSamplerBase::writeForceField
(
    const List<vector>& faceForces
)
{
    if (!fsiActive_)
    {
        return;
    }

    if (faceForces.size() != surface_->size())
    {
        FatalErrorInFunction
            << "Surface sampler FSI: expected " << surface_->size()
            << " per-face forces but received " << faceForces.size()
            << nl << exit(FatalError);
    }

    const faceList& faces = surface_->surfFaces();

    List<vector> vertexForces(surfacePoints().size(), vector::zero);

    forAll(faces, f)
    {
        const face& fv = faces[f];
        const vector Ff = faceForces[f];

        // Equal split over the face vertices: the vertex sum preserves the
        // total force (each face contributes Ff exactly once)
        const scalar w = 1.0/scalar(fv.size());

        forAll(fv, k)
        {
            vertexForces[fv[k]] += w*Ff;
        }
    }

    // Registry the global-frame force per vertex for the preCICE adapter
    *fsiForceFieldPtr_ = vertexForces;
}


Foam::tensor Foam::fv::surfaceSamplerBase::rotationTensor
(
    const vector& axis,
    const scalar radians
)
{
    // Same arithmetic as actuatorLineElement::rotate (from SOWFA), so the
    // surface stays in lockstep with the blade elements
    tensor RM;
    const scalar angle = radians;

    RM.xx() = sqr(axis.x()) + (1.0 - sqr(axis.x()))*cos(angle);
    RM.xy() = axis.x()*axis.y()*(1.0 - cos(angle)) - axis.z()*sin(angle);
    RM.xz() = axis.x()*axis.z()*(1.0 - cos(angle)) + axis.y()*sin(angle);
    RM.yx() = axis.x()*axis.y()*(1.0 - cos(angle)) + axis.z()*sin(angle);
    RM.yy() = sqr(axis.y()) + (1.0 - sqr(axis.y()))*cos(angle);
    RM.yz() = axis.y()*axis.z()*(1.0 - cos(angle)) - axis.x()*sin(angle);
    RM.zx() = axis.x()*axis.z()*(1.0 - cos(angle)) - axis.y()*sin(angle);
    RM.zy() = axis.y()*axis.z()*(1.0 - cos(angle)) + axis.x()*sin(angle);
    RM.zz() = sqr(axis.z()) + (1.0 - sqr(axis.z()))*cos(angle);

    return RM;
}


void Foam::fv::surfaceSamplerBase::initializeFsiGeometry()
{
    if (!fsiActive_)
    {
        return;
    }

    // The reference is the post-setup configuration: the imported vertices
    // and face centroids after the static azimuth/tilt/yaw transforms
    fsiReferencePoints_ = surfacePoints();
    fsiReferenceCentroids_ = positions_;

    fsiRotationPoint_ = vector::zero;
    fsiRotationAxis_ = vector(0, 0, 1);
    fsiTotalAngle_ = 0.0;
    fsiGeometryInitialized_ = true;

    // Publish the reference vertices: the preCICE point cloud is fixed and the
    // mapping is built once from this configuration
    writeCoordinateField();

    // Optionally write the reference cloud to a plain file, so an external
    // structural participant can register the same vertices
    if (!fsiCoordFileName_.empty())
    {
        OFstream os(fsiCoordFileName_);
        os << "# FSI reference vertices (" << fsiReferencePoints_.size()
           << ")" << nl;

        forAll(fsiReferencePoints_, i)
        {
            os << fsiReferencePoints_[i].x() << ' '
               << fsiReferencePoints_[i].y() << ' '
               << fsiReferencePoints_[i].z() << nl;
        }

        Info<< "Surface sampler: wrote the FSI reference cloud to "
            << fsiCoordFileName_ << endl;
    }

    Info<< "Surface sampler: FSI geometry reference captured ("
        << fsiReferencePoints_.size() << " vertices)" << endl;
}


void Foam::fv::surfaceSamplerBase::accumulateFsiRotation
(
    const point& rotationPoint,
    const vector& axis,
    const scalar radians
)
{
    fsiRotationPoint_ = rotationPoint;
    fsiRotationAxis_ = axis;
    fsiTotalAngle_ += radians;
}


void Foam::fv::surfaceSamplerBase::fsiUpdateGeometry()
{
    if (!fsiActive_ || !fsiGeometryInitialized_)
    {
        return;
    }

    const vectorIOField& u = *fsiDispFieldPtr_;

    if (u.size() != fsiReferencePoints_.size())
    {
        FatalErrorInFunction
            << "FSI displacement field \"" << fsiDispFieldName_ << "\" has "
            << u.size() << " entries but the surface has "
            << fsiReferencePoints_.size() << " vertices" << nl
            << exit(FatalError);
    }

    const tensor R = rotationTensor(fsiRotationAxis_, fsiTotalAngle_);

    // current = rotationPoint + R & (reference + u_fsi - rotationPoint)
    pointField curVerts(fsiReferencePoints_.size());

    forAll(curVerts, i)
    {
        curVerts[i] =
            fsiRotationPoint_
          + (R & (fsiReferencePoints_[i] + u[i] - fsiRotationPoint_));
    }

    // Publish the current vertices (the element FSI update consumes them)
    fsiCurrentPoints_ = curVerts;

    // Refresh the face geometry from the deformed vertices
    PrimitivePatch<faceList, pointField> curPatch
    (
        surface_->surfFaces(),
        curVerts
    );

    positions_ = curPatch.faceCentres();
    normals_ = curPatch.faceNormals();
    areas_ = curPatch.magFaceAreas();

    updateBodyFrame();
}


// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

Foam::fv::surfaceSamplerBase::~surfaceSamplerBase()
{}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

Foam::scalar Foam::fv::surfaceSamplerBase::cellSize(const point& X) const
{
    scalar h = VGREAT;

    const label cellI = mesh_.findCell(X);

    if (cellI >= 0)
    {
        h = Foam::cbrt(mesh_.V()[cellI]);
    }

    // Reduce the sentinel over all processors; the rank owning the containing
    // cell contributes its local cell size
    reduce(h, minOp<scalar>());

    if (!(h < VGREAT))
    {
        FatalErrorInFunction
            << "Surface sample at " << X << " not found in mesh" << nl
            << exit(FatalError);
    }

    return h;
}


Foam::scalar Foam::fv::surfaceSamplerBase::kernel(const scalar r)
{
    // Eq. 8: smoothed four-point cosine kernel, support |r| <= 2.5
    const scalar ar = mag(r);

    if (ar <= 1.5)
    {
        return
            0.25
          + Foam::sin
            (
                constant::mathematical::pi*(2.0*ar + 1.0)/4.0
            )/(2.0*constant::mathematical::pi)
          - Foam::sin
            (
                constant::mathematical::pi*(2.0*ar - 1.0)/4.0
            )/(2.0*constant::mathematical::pi);
    }
    else if (ar <= 2.5)
    {
        return
            0.625
          - 0.25*ar
          - Foam::sin
            (
                constant::mathematical::pi*(2.0*ar - 1.0)/4.0
            )/(2.0*constant::mathematical::pi);
    }

    return 0.0;
}


Foam::vector Foam::fv::surfaceSamplerBase::interpolateVelocity
(
    const point& X,
    const volVectorField& U,
    const scalar h
) const
{
    // Eq. 7: kernel sum over the local cells within the kernel support,
    // delta_h*V = phi_x*phi_y*phi_z for a uniform local cell size h
    vector sumU = vector::zero;
    scalar sumW = 0.0;
    const scalar radius = 2.5*h;

    forAll(mesh_.cells(), cellI)
    {
        const vector d = mesh_.C()[cellI] - X;

        // Bounding-box prefilter on the kernel support
        if
        (
            mag(d.x()) > radius
         || mag(d.y()) > radius
         || mag(d.z()) > radius
        )
        {
            continue;
        }

        const scalar w =
            kernel(d.x()/h)*kernel(d.y()/h)*kernel(d.z()/h);

        if (w > 0.0)
        {
            sumU += w*U[cellI];
            sumW += w;
        }
    }

    // Every rank holds the full node list but only its local cells, so the
    // kernel sums must be reduced globally. returnReduce() returns the
    // reduced copy and leaves its argument unchanged, so the result has to
    // be assigned back: a discarded return keeps the rank-local partial
    // sums, making each rank interpolate from its own subset (a rank with
    // no cell in the stencil would report a zero velocity) instead of the
    // paper's Eq. 7 global kernel average.
    sumW = returnReduce(sumW, sumOp<scalar>());
    sumU = returnReduce(sumU, sumOp<vector>());

    if (sumW < SMALL)
    {
        // No cells within the kernel support (e.g. an off-wall probe outside
        // the mesh); treated as a zero velocity
        return vector::zero;
    }

    return sumU/sumW;
}


void Foam::fv::surfaceSamplerBase::distributeForce
(
    volVectorField& ff,
    const List<vector>& nodeForcesGlobal,
    const List<scalar>& nodeH,
    const List<List<label>>* candidates
) const
{
    if (candidates)
    {
        // Bounded path: each node visits only its precomputed candidate cells
        forAll(nodeForcesGlobal, i)
        {
            const point& X = positions_[i];
            const vector F = nodeForcesGlobal[i];
            const scalar h = nodeH[i];
            const List<label>& cells = (*candidates)[i];

            forAll(cells, k)
            {
                const label cellI = cells[k];
                const vector d = mesh_.C()[cellI] - X;

                const scalar w
                (
                    kernel(d.x()/h)
                  * kernel(d.y()/h)
                  * kernel(d.z()/h)
                );

                if (w > 0.0)
                {
                    // Eq. 18 with the paper's negative sign: the distributed
                    // force acts on the flow, F_i acts on the body
                    ff[cellI] -= F*(w/mesh_.V()[cellI]);
                }
            }
        }

        return;
    }

    forAll(nodeForcesGlobal, i)
    {
        const point& X = positions_[i];
        const vector F = nodeForcesGlobal[i];
        const scalar h = nodeH[i];
        const scalar radius = 2.5*h;

        // Every rank holds the full (replicated) node list and loops over its
        // local cells only, so each receiving cell is written exactly once by
        // its owner and every node contributes to every cell in its stencil
        forAll(mesh_.cells(), cellI)
        {
            const vector d = mesh_.C()[cellI] - X;

            // Bounding-box prefilter on the kernel support
            if
            (
                mag(d.x()) > radius
             || mag(d.y()) > radius
             || mag(d.z()) > radius
            )
            {
                continue;
            }

            const scalar w
            (
                kernel(d.x()/h)
              * kernel(d.y()/h)
              * kernel(d.z()/h)
            );

            if (w > 0.0)
            {
                // Eq. 18 with the paper's negative sign: the distributed
                // force acts on the flow, F_i acts on the body
                ff[cellI] -= F*(w/mesh_.V()[cellI]);
            }
        }
    }
}


// ************************************************************************* //
